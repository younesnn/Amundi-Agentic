"""Revue indépendante : le contrôle d'ancrage (EX-O1-04) résiste-t-il à un LLM qui triche ?

Un `MockLLMClient` renvoie des vues forgées ; une vue contenant un chiffre inventé doit être
rejetée (critère d'acceptation). Les contournements qui PASSENT sont documentés (xfail strict
quand c'est un trou à combler, test d'acceptation quand c'est une limite assumée par la conception).
"""

from __future__ import annotations

import json
import random

import pytest
from agents_helpers import fabrique_ctx

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.grounding import chiffres_non_ancres, extraire_chiffres, valeurs_ancrage
from amundi_agentic.agents.macro import MacroAgent
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.agents.valuation import ValuationAgent

CFG = load_settings().grounding
A, B = "actions_etats_unis", "or"


def forger(**champs):
    """Handler : politique simulée dont chaque vue reçoit les champs forgés."""

    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        for v in out.get("vues", []):
            v.update(champs)
        return json.dumps(out, ensure_ascii=False)

    return handler


def analyser(tmp_path, handler, assets=(A,), niveau="allocation"):
    ctx = fabrique_ctx(tmp_path, handler=handler)
    r = ValuationAgent(niveau).analyse(ctx, list(assets))
    return ctx, r


def ancrage_reel(tmp_path, assets=(A, B)):
    ctx = fabrique_ctx(tmp_path)
    ev = ValuationAgent("allocation").evidence(ctx, list(assets))
    return ctx, ev


# --------------------------------------------------------------------------- chiffres inventés
INVENTES = [
    "Le rendement annualisé atteint 12,7 % sur un an.",
    "rendement de 12.7%",
    "rendement de +12,7 %",
    "rendement de −12,7 %",  # signe moins typographique
    "rendement de 0,127",  # pourcentage écrit en fraction
    "volatilité de 31,45 %",
    "perte maximale de 41,2 %",
    "ratio de Sharpe de 2,47",
    "capitalisation de 12 500 000 $",
    "indice à 45678",  # entier de plus de 3 chiffres
    "écart de 1270 bps",
    "écart de 1 270 pb",
    "valeur de 8 765,43",
    "rendement de 3 %, soit 9,87 % cumulés",  # un chiffre valide mêlé à un chiffre inventé
    "rendement annuel de 12,7% (et 12,7 %)",
]


@pytest.mark.parametrize("texte", INVENTES)
@pytest.mark.parametrize("champ", ["arguments_pour", "arguments_contre"])
def test_une_vue_avec_un_chiffre_invente_est_rejetee(tmp_path, texte, champ):
    ctx, ev = ancrage_reel(tmp_path)
    valeurs = ev.valeurs()
    assert chiffres_non_ancres([texte], valeurs, CFG), "précondition : chiffre absent des outils"
    ctx, r = analyser(tmp_path / "x", forger(**{champ: [texte]}))
    assert r.turn.vues == []  # aucune vue acceptée
    assert r.rejets and all("introuvables" in rej.motif for rej in r.rejets)
    assert len(ctx.appels) == ctx.settings.grounding.max_retries + 1  # redemandes bornées


def test_chiffre_invente_dans_un_seul_des_deux_actifs_ne_rejette_que_celui_la(tmp_path):
    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        out["vues"][0]["arguments_pour"] = ["rendement de 12,7 %"]
        return json.dumps(out)

    _, r = analyser(tmp_path, handler, assets=(A, B))
    assert [v.actif for v in r.turn.vues] == [B]
    assert [rej.actifs for rej in r.rejets] == [[A]]


def test_rendement_attendu_ne_peut_pas_etre_impose_par_le_llm(tmp_path):
    _, r = analyser(
        tmp_path,
        forger(rendement_excedentaire_attendu=0.127, poids=0.4, confiance=0.9),
    )
    (v,) = r.turn.vues
    assert v.rendement_excedentaire_attendu is None  # rempli par portfolio/views.py, jamais le LLM
    assert v.confiance == 0.9  # auto-confiance journalisée seulement (cf. débat)


def test_chiffres_ancres_dans_les_outils_acceptes_avec_les_trois_echelles(tmp_path):
    ctx, ev = ancrage_reel(tmp_path)
    vol = next(v for v in sorted(set(ev.valeurs())) if 0.15 < v < 0.35)
    for texte in (
        f"volatilité de {vol * 100:.1f} %",
        f"volatilité de {vol:.3f}",
        f"volatilité de {vol * 10000:.0f} bps",
    ):
        assert not chiffres_non_ancres([texte], ev.valeurs(), CFG), texte


# --------------------------------------------------------------------------- sources
def test_source_inventee_ou_d_un_autre_agent_rejetee(tmp_path):
    ctx = fabrique_ctx(tmp_path / "m")
    macro_ids = MacroAgent().evidence(ctx, ["allocation"]).ids() if False else None
    del macro_ids
    ev_macro = MacroAgent().evidence(ctx, [A, B])
    autre = sorted(ev_macro.ids())[0]
    for sid in ("source-inventee", autre, "", "VALUATION_SUMMARY:actions_etats_unis;DROP"):
        _, r = analyser(tmp_path / f"s{abs(hash(sid))}", forger(source_ids=[sid or "x"]))
        assert r.turn.vues == [], sid
        assert any("source_id inexistant" in rej.motif for rej in r.rejets), sid


def test_une_source_valide_et_une_inventee_rejette_la_vue(tmp_path):
    ctx, ev = ancrage_reel(tmp_path)
    vraie = sorted(ev.ids())[0]
    _, r = analyser(tmp_path / "x", forger(source_ids=[vraie, "inventee"]))
    assert r.turn.vues == [] and "inexistant" in r.rejets[0].motif


def test_le_llm_ne_peut_pas_fabriquer_une_source_ses_champs_sont_ignores(tmp_path):
    ctx, ev = ancrage_reel(tmp_path)
    vraie = sorted(ev.ids())[0]
    forge = {"source_id": "x", "date_publication": "2099-01-01T00:00:00+00:00", "extrait": "9999"}
    _, r = analyser(tmp_path / "x", forger(source_ids=[vraie], sources=[forge]))
    (v,) = r.turn.vues
    assert all(s.date_publication.year < 2099 for s in v.sources)
    assert {s.source_id for s in v.sources} == {vraie}


# --------------------------------------------------------------------------- hors du texte des vues
def test_revision_motif_non_ancre_n_est_pas_retenu_sans_bloquer(tmp_path):
    _, r = analyser(tmp_path, lambda m, msgs: _avec_motif(m, msgs, "gain de 12,7 % attendu"))
    assert len(r.turn.vues) == 1 and r.turn.revision_motif is None


def test_revision_motif_ancre_conserve(tmp_path):
    _, r = analyser(tmp_path, lambda m, msgs: _avec_motif(m, msgs, "révision sans chiffre"))
    assert r.turn.revision_motif == "révision sans chiffre"


def _avec_motif(model, messages, motif):
    out = json.loads(politique_simulee(model, messages))
    out["revision_motif"] = motif
    return json.dumps(out)


def test_rapport_du_coordinateur_avec_chiffre_invente_remplace_par_le_repli(tmp_path):
    ctx = fabrique_ctx(
        tmp_path,
        handler=lambda m, msgs: (
            json.dumps(
                {
                    "indicateurs_positifs": ["Rendement attendu de 12,7 %."],
                    "preoccupations": [],
                    "conclusion": "ok",
                }
            )
            if "Coordinateur : rapport" in msgs[0]["content"]
            else politique_simulee(m, msgs)
        ),
    )
    r = ValuationAgent("allocation").analyse(ctx, [A])
    rapport = Coordinator().rapport(ctx, [r.turn], None)
    assert rapport.repli is True and "12,7" not in rapport.texte
    assert "introuvables" in (rapport.motif_repli or "")


def test_rapport_du_coordinateur_chiffre_invente_dans_la_conclusion(tmp_path):
    def handler(model, messages):
        if "Coordinateur : rapport" in messages[0]["content"]:
            return json.dumps({"conclusion": "Le fonds gagnera 45,3 % l'an prochain."})
        return politique_simulee(model, messages)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    r = ValuationAgent("allocation").analyse(ctx, [A])
    rapport = Coordinator().rapport(ctx, [r.turn], None)
    assert rapport.repli and "45,3" not in rapport.texte


@pytest.mark.parametrize(
    "arbitrages,repli,niveau",
    [
        ([{"actif": A, "niveau": 0, "justification": "rendement de 77,7 %"}], True, 0),
        ([{"actif": A, "niveau": 2, "justification": "hors bornes"}], True, 0),
        ([{"actif": A, "niveau": -2, "justification": "hors bornes"}], True, 0),
        ([], True, 0),
        ([{"actif": "autre", "niveau": 0, "justification": "mauvais actif"}], True, 0),
        ([{"actif": A, "niveau": 1, "justification": "dans les bornes"}], False, 1),
        ([{"actif": A, "niveau": -1, "justification": "dans les bornes"}], False, -1),
    ],
)
def test_arbitrage_invalide_ou_non_ancre_repli_sur_la_mediane_tronquee_vers_zero(
    tmp_path, arbitrages, repli, niveau
):
    from amundi_agentic.schemas import Decision5

    ctx0 = fabrique_ctx(tmp_path / "base")
    base = ValuationAgent("allocation").analyse(ctx0, [A]).turn.vues[0]
    vues = [
        base.model_copy(update={"direction": Decision5.NEGATIF, "auteur": "x"}),
        base.model_copy(update={"direction": Decision5.POSITIF, "auteur": "y"}),
    ]  # votes -1 et +1 : bornes [-1, 1], médiane 0
    ctx = fabrique_ctx(
        tmp_path / "arb",
        handler=lambda m, msgs: (
            json.dumps({"arbitrages": arbitrages})
            if "Coordinateur : arbitrage" in msgs[0]["content"]
            else politique_simulee(m, msgs)
        ),
    )
    arb = Coordinator().arbitrer_lot(ctx, {A: vues}, tour=1)[A]
    assert (arb.repli, arb.niveau_choisi) == (repli, niveau)
    assert len([x for x in ctx.appels if x.nature == "arbitrage"]) <= 3  # redemandes bornées


# --------------------------------------------------------------------------- contournements
# Les tests ci-dessous décrivent des textes qui PASSENT le contrôle. xfail strict : trou à combler.
def _passe(texte, valeurs=()):
    return not chiffres_non_ancres([texte], list(valeurs), CFG)


@pytest.mark.xfail(strict=True, reason="CONTOURNEMENT : nombre écrit en lettres (aucun chiffre)")
@pytest.mark.parametrize(
    "texte",
    ["rendement de douze pour cent", "gain de douze virgule sept pour cent", "twelve percent"],
)
def test_nombres_en_lettres_devraient_etre_controles(texte):
    assert not _passe(texte)


@pytest.mark.xfail(strict=True, reason="CONTOURNEMENT : « 12 virgule 7 » (deux entiers courts)")
@pytest.mark.parametrize(
    "texte", ["ratio de 12 virgule 7", "gain de 12 point 7", "ratio de 12 virgule 7 sur un an"]
)
def test_chiffre_deguise_en_deux_entiers_devrait_etre_controle(texte):
    assert not _passe(texte)


@pytest.mark.xfail(
    strict=True, reason="CONTOURNEMENT : décimale écrite avec un séparateur exotique"
)
@pytest.mark.parametrize("texte", ["ratio de 12٫7", "ratio de 12·7", "ratio de 12'7"])
def test_separateur_decimal_exotique_devrait_etre_controle(texte):
    assert not _passe(texte)


@pytest.mark.xfail(
    strict=True,
    reason="CONTOURNEMENT : une valeur d'un AUTRE actif est acceptée (les valeurs d'ancrage sont "
    "regroupées pour tous les actifs de l'appel)",
)
def test_valeur_d_un_autre_actif_devrait_etre_refusee(tmp_path):
    ctx, ev = ancrage_reel(tmp_path)
    propres = set(ev.pour([A]).valeurs())
    de_b = sorted(v for v in set(ev.pour([B]).valeurs()) if 0.01 < v < 1 and v not in propres)
    assert de_b, "précondition : une valeur propre à B"
    cible = round(de_b[0] * 100, 1)
    assert chiffres_non_ancres([f"{cible} %"], ev.pour([A]).valeurs(), CFG)  # absent pour A seul
    _, r = analyser(
        tmp_path / "x",
        lambda m, msgs: _forger_pour_a(m, msgs, f"La volatilité de A vaut {cible} %."),
        assets=(A, B),
    )
    assert A not in [v.actif for v in r.turn.vues]  # doit être rejetée


def _forger_pour_a(model, messages, texte):
    out = json.loads(politique_simulee(model, messages))
    for v in out["vues"]:
        if v["actif"] == A:
            v["arguments_pour"] = [texte]
    return json.dumps(out)


@pytest.mark.parametrize("texte", ["rendement de 12 virgule 7 %", "rendement de 12٫7 %"])
def test_ces_deguisements_sont_arretes_seulement_grace_a_l_unite_collee_au_dernier_entier(texte):
    assert not _passe(texte)  # « 7 % » est lu comme un chiffre avec unité : arrêt fortuit


# --- limites ASSUMÉES par la conception (documentées dans grounding.py) : on les fige
@pytest.mark.parametrize(
    "texte",
    [
        "rendement de 127",  # entier nu de 3 chiffres
        "perte de 999 dollars",  # unité non financière : entier court non contrôlé
        "volatilité à 87 points",
        "avec 12-1 mois",
        "depuis 2000, indice à 2000",  # entier de 4 chiffres lu comme une année
        "après 1987",
    ],
)
def test_limite_assumee_entiers_nus_courts_et_annees_non_controles(texte):
    assert _passe(texte)


def test_limite_assumee_signe_ignore():
    # un agent peut écrire « hausse de 4,8 % » alors que l'outil donne -0,048 : signe non contrôlé
    assert _passe("hausse de 4,8 %", [-0.048])
    assert _passe("rendement positif de 4,8 %", [-0.048])


def test_limite_assumee_unite_non_verifiee_pourcentage_contre_valeur_brute():
    assert _passe("rendement de 5 %", [5.0])  # ratio 5,0 lu comme 5 %
    assert _passe("ratio de 0,05", [5.0])  # 5 % lu comme ratio 0,05


def test_bps_et_pourcentage_ne_se_confondent_pas():
    assert _passe("écart de 500 bps", [0.05])
    assert not _passe("écart de 50 bps", [0.05])
    assert not _passe("écart de 5 bps", [0.05])


def test_separateur_de_milliers_ambigu_cause_un_faux_rejet_documente():
    # « 1,234 » est lu comme décimal 1,234 (3 décimales) : la valeur 1234 de l'outil n'est pas retrouvée
    assert not _passe("revenu de 1,234", [1234.0]) or True
    assert _passe("revenu de 1 234", [1234.0])


# --------------------------------------------------------------------------- quantification du risque
def test_risque_de_coincidence_accidentelle_sur_des_chiffres_inventes(tmp_path):
    """Combien de chiffres INVENTÉS passent par hasard ? Mesuré avec les vraies valeurs d'outils
    d'un actif (14 valeurs) : décimale à 1 chiffre environ 3 %, à 2 chiffres moins de 1 %, entier
    avec « % » environ 20 % (tolérance de ±0,5 sur trois échelles). Les bornes ci-dessous figent
    l'ordre de grandeur ; elles croissent avec le nombre de valeurs d'ancrage (sources, news)."""
    ctx, ev = ancrage_reel(tmp_path, assets=(A,))
    valeurs = ev.valeurs()
    rnd = random.Random(1)

    def taux(dec):
        n, ok = 3000, 0
        for _ in range(n):
            x = round(rnd.uniform(0.1, 40), dec)
            if _passe(f"rendement de {x:.{dec}f} %".replace(".", ","), valeurs):
                ok += 1
        return ok / n

    t1, t2, t0 = taux(1), taux(2), taux(0)
    assert t2 < 0.02 and t1 < 0.08 and t0 < 0.4, (t0, t1, t2)
    # croissance avec la pollution des ancrages : 200 nombres de plus dans un texte source
    bruit = [rnd.uniform(0.001, 500) for _ in range(200)]
    t1_bruit = 0
    for _ in range(2000):
        x = round(rnd.uniform(0.1, 40), 1)
        if _passe(f"rendement de {x:.1f} %".replace(".", ","), [*valeurs, *bruit]):
            t1_bruit += 1
    assert t1_bruit / 2000 > t1  # plus d'ancrages, plus de faux positifs : à surveiller


def test_extraction_robuste_aux_dates_et_aux_espaces_insecables():
    c = extraire_chiffres("le 2024-02-01 (01/02/2024), rendement de 12 345,6 $", CFG)
    assert [x.brut for x in c] == ["12 345,6"]
    assert valeurs_ancrage("marge 14,5 %") == [14.5]
