"""Revue indépendante, 2e passe : nombres en lettres, décimales déguisées, faux rejets, taux de
coïncidences résiduel, ancrage PAR ACTIF (valeurs communes, pairs, sources)."""

from __future__ import annotations

import json
import random

import pytest
from agents_helpers import fabrique_ctx

from amundi_agentic.agents.grounding import Ancre, chiffres_non_ancres
from amundi_agentic.agents.macro import MacroAgent
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.agents.valuation import ValuationAgent

CFG = load_settings().grounding
A, B = "actions_etats_unis", "or"


def rejete(texte, ancres=()):
    return bool(chiffres_non_ancres([texte], list(ancres), CFG))


# --------------------------------------------------------------------------- le bloquant, rejoué
INVENTES_REJETES = [
    "rendement de douze pour cent", "gain de twelve percent", "douze virgule sept pour cent",
    "twelve point seven percent", "ratio de 12 virgule 7", "gain de 12 point 7",
    "ratio de 12٫7", "ratio de 12·7", "ratio de 12'7", "ratio de 12’7",
    "ratio de un virgule deux", "un virgule deux", "sharpe de deux virgule cinq",
    "rendement de dix-sept %", "gain de vingt-deux %", "perte de cent vingt $",
    "capitalisation de 3 milliards", "capitalisation de trois milliards", "douze millions",
    "twelve million", "fifty basis points", "cinquante points de base", "twelve bps",
    "rendement de dix pour cent", "douze pour cent par an", "rendement de quatre-vingt-dix pour cent",
    "a hundred and twenty percent", "douze pourcent", "twelve per cent", "gain: onze %",
    "12.7 percent", "rendement de douze point sept", "1,2 milliards", "rendement de dix-sept",
    "gain de vingt-deux", "perte de cent vingt", "rendement de quatre-vingt-dix",
    "ratio de １２,７",  # chiffres pleine chasse
    "ratio de ١٢٫٧",  # chiffres arabes-indiens
]  # fmt: skip


@pytest.mark.parametrize("texte", INVENTES_REJETES)
def test_chiffre_invente_en_lettres_ou_deguise_est_rejete(texte):
    assert rejete(texte), f"CONTOURNEMENT : {texte!r}"


@pytest.mark.parametrize("texte", INVENTES_REJETES)
def test_les_memes_textes_passent_si_la_valeur_est_ancree_dans_un_outil_ou_un_texte(texte):
    """Anti faux-rejet : une valeur réellement présente (12 ; 12,7 ; 17 ; 22 ; 120 ; 90 ; 3 milliards)
    ne doit pas faire rejeter la vue. On teste avec des ancrages de texte source (échelle 1)."""
    ancres = [Ancre(v, "texte") for v in (12, 12.7, 1.2, 2.5, 17, 22, 120, 90, 3e9, 3, 50, 10, 11)]
    ancres += [Ancre(v, "outil") for v in (0.127, 0.12, 0.17, 0.22, 0.1, 0.9, 0.11, 0.5, 0.005)]
    ancres += [Ancre(v, "texte") for v in (1_200_000_000, 12_000_000, 3_000_000_000, 100, 120)]
    if "１２" in texte or "١٢" in texte:
        assert not rejete(texte, ancres)  # chiffres exotiques ramenés en ASCII
    else:
        assert not rejete(texte, ancres), f"faux rejet malgré ancrage : {texte!r}"


# encore ouverts : mesurés, non bloquants
@pytest.mark.parametrize(
    "texte",
    [
        "gain de trois et demi pour cent",
        "douze et demi pour cent",
        "twelve and a half percent",
    ],
)
def test_residuel_fractions_parlees_et_demi(texte):
    assert rejete(texte)


@pytest.mark.parametrize(
    "texte",
    [
        "hausse de quinze", "environ douze", "ratio de trois", "rendement de douze",
        "douze analystes", "gain de trois", "croissance de six", "un quart", "trois quarts",
    ],
)  # fmt: skip
def test_limite_assumee_petit_mot_nombre_simple_sans_unite_comme_entier_nu(texte):
    """Cohérent avec la règle des entiers nus courts : un petit mot-nombre simple sans unité passe,
    même après un mot de contexte (comme « 12 » sans unité)."""
    assert not rejete(texte)


@pytest.mark.parametrize(
    "texte",
    [
        "rendement de seventeen", "rendement de twenty-four", "gain de twenty one",
        "perte de vingt-deux", "rendement de dix-sept", "gain de cinq cent",
        "ratio de quatre-vingt-dix",
    ],
)  # fmt: skip
def test_mot_nombre_compose_apres_un_mot_de_contexte_financier_est_controle(texte):
    assert rejete(texte), f"CONTOURNEMENT : {texte!r}"


@pytest.mark.parametrize(
    "texte",
    [
        "twenty-four hours", "twenty one", "mille et une nuits", "cinq cent", "seventeen",
        "dix-sept", "twenty-two analysts", "cent entreprises", "quatre-vingt-dix jours",
    ],
)  # fmt: skip
def test_meme_mot_nombre_compose_sans_contexte_financier_n_est_pas_rejete(texte):
    assert not rejete(texte), f"FAUX REJET : {texte!r}"


def test_contexte_financier_lu_dans_la_configuration_et_sensible_a_la_casse_et_aux_accents():
    assert "rendement" in CFG.contexte_financier and "return" in CFG.contexte_financier
    assert rejete("Rendement de twenty-four") and rejete("RENDEMENT DE TWENTY-FOUR")
    assert rejete("Volatilité de vingt-deux") and rejete("Bénéfice de vingt-deux")
    assert not rejete("les twenty-four hours du marché")  # contexte non adjacent


def test_la_valeur_ancree_fait_passer_les_composes_apres_contexte():
    ancres = [Ancre(17, "texte"), Ancre(0.24, "outil"), Ancre(0.22, "outil"), Ancre(500, "texte")]
    for texte in ("rendement de seventeen", "rendement de dix-sept", "gain de vingt-deux %",
                  "gain de cinq cent"):  # fmt: skip
        assert not rejete(texte, ancres), texte


# --------------------------------------------------------------------------- faux rejets
LEGITIMES = [
    "en 2023", "3 analystes", "un risque", "deux fois", "premier trimestre", "un tiers",
    "52 semaines", "le 2024-02-01", "le 1er février", "Apple Inc.", "One Belt One Road",
    "un an", "one-year", "one year", "trois mois", "la une", "l'un des", "une hausse", "un peu",
    "quatre trimestres", "les deux", "tout un chacun", "sept jours", "dix jours ouvrés",
    "deuxième semestre", "S&P 500", "Nasdaq 100", "Fortune 500", "Top 10", "Dow Jones 30",
    "Q1 2024", "one of the", "no one", "trois pays", "cent jours", "Seven & i Holdings",
    "Three Gorges", "Cinq à sept", "dix ans", "10 ans", "as one", "one", "un", "two", "deux",
    "trois", "douze mois", "douze analystes", "cent entreprises", "Louis XIV", "Henri IV",
    "premier", "second", "une fois par an", "au moins deux", "un seul agent", "à un horizon",
]  # fmt: skip


@pytest.mark.parametrize("texte", LEGITIMES)
def test_texte_legitime_sans_quantite_financiere_n_est_pas_rejete(texte):
    assert not rejete(texte), f"FAUX REJET : {texte!r}"


def test_taux_de_faux_rejets_sur_les_textes_legitimes():
    faux = [t for t in LEGITIMES if rejete(t)]
    assert not faux and len(LEGITIMES) >= 55


@pytest.mark.parametrize("texte", ["twenty-four hours", "mille et une nuits", "cinq cent"])
def test_faux_rejets_connus_de_mots_nombres_composes(texte):
    assert not rejete(texte)


# --------------------------------------------------------------------------- coïncidences résiduelles
def _ancres_reelles(tmp_path, actif=A):
    ctx = fabrique_ctx(tmp_path)
    return ValuationAgent("allocation").evidence(ctx, [A, B]).ancres_pour(actif)


def _taux(ancres, dec, unite, n=3000, graine=1):
    rnd = random.Random(graine)
    ok = 0
    for _ in range(n):
        x = round(rnd.uniform(0.1, 40), dec)
        if not rejete(f"rendement de {x:.{dec}f} {unite}".replace(".", ","), ancres):
            ok += 1
    return ok / n


def test_taux_de_coincidences_residuel_avec_14_valeurs_d_ancrage_reelles(tmp_path):
    ancres = _ancres_reelles(tmp_path)
    assert len(ancres) == 14 and all(isinstance(a, Ancre) for a in ancres)
    entier, une, deux = _taux(ancres, 0, "%"), _taux(ancres, 1, "%"), _taux(ancres, 2, "%")
    assert entier < 0.05 and une < 0.04 and deux < 0.01, (entier, une, deux)  # ~2,4 / 1,9 / 0,25 %
    assert _taux(ancres, 0, "bps") == 0.0  # pas de coïncidence en points de base


def test_taux_de_coincidences_residuel_avec_200_valeurs_d_ancrage(tmp_path):
    """200 ancrages : (1) répartition réaliste (log-uniforme sur 1e-4 à 1e4, comme des sorties
    d'outils et des textes sources variés) ; (2) PIRE CAS : 186 valeurs toutes dans la plage des
    pourcentages plausibles. Le taux de coïncidence croît avec la densité d'ancrages."""
    import math

    rnd = random.Random(7)
    base = _ancres_reelles(tmp_path)
    realiste = [
        *base,
        *(Ancre(math.exp(rnd.uniform(math.log(1e-4), math.log(1e4))), "outil") for _ in range(186)),
    ]
    entier, une, deux = _taux(realiste, 0, "%"), _taux(realiste, 1, "%"), _taux(realiste, 2, "%")
    # mesuré : environ 27 % / 13 % / 1,6 % (contre 2,4 / 1,9 / 0,25 % avec 14 valeurs)
    assert 0.05 < entier < 0.40 and une < 0.20 and deux < 0.04, (entier, une, deux)
    dense = [*base, *(Ancre(rnd.uniform(0.001, 0.5), "outil") for _ in range(186))]
    d_entier, d_une, d_deux = _taux(dense, 0, "%"), _taux(dense, 1, "%"), _taux(dense, 2, "%")
    # pire cas : plus de la moitié des entiers en % sont acceptés par hasard (limite à connaître)
    assert d_entier > 0.3 and d_une > 0.15 and d_deux < 0.10, (d_entier, d_une, d_deux)
    assert d_une > _taux(base, 1, "%") and d_entier > _taux(base, 0, "%")


def test_les_ancres_d_outil_sont_comparees_a_l_echelle_de_l_unite(tmp_path):
    a = [Ancre(0.127, "outil")]
    assert not rejete("rendement de 12,7 %", a) and rejete("rendement de 0,127 %", a)
    assert not rejete("écart de 1270 bps", a) and rejete("écart de 12,7 bps", a)
    assert not rejete("ratio de 0,127", a) and rejete("ratio de 12,7", a)  # sans unité : échelle 1
    t = [Ancre(12.7, "texte")]  # lue dans un texte source : telle quelle
    assert not rejete("marge de 12,7 %", t) and rejete("marge de 1270 %", t)


def test_tolerance_relative_des_entiers_est_plus_stricte_que_l_ancienne(tmp_path):
    a = [Ancre(0.60, "outil")]
    assert not rejete("rendement de 60 %", a)
    assert rejete("rendement de 61 %", a)  # l'ancienne tolérance absolue de ±0,5 n'aurait pas suffi
    assert rejete("rendement de 59 %", a)
    a2 = [Ancre(0.0049, "outil")]
    assert not rejete("0,5 %", a2) and rejete("1 %", a2)


# --------------------------------------------------------------------------- ancrage par actif
def _handler_citant(texte_pour, cible=A):
    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        for v in out.get("vues", []):
            if v["actif"] == cible:
                v["arguments_pour"] = [texte_pour]
        return json.dumps(out, ensure_ascii=False)

    return handler


def _valeur_propre(tmp_path, actif, autre):
    ctx = fabrique_ctx(tmp_path)
    ev = ValuationAgent("allocation").evidence(ctx, [A, B])
    propres = {a.valeur for a in ev.ancres_pour(actif)}
    de_autre = sorted(a.valeur for a in ev.ancres_pour(autre) if a.valeur not in propres)
    return next(v for v in de_autre if 0.01 < v < 1)


def test_valeur_de_l_actif_a_citee_pour_b_est_rejetee_et_pour_a_acceptee(tmp_path):
    vol_a = _valeur_propre(tmp_path / "a", B, A)  # valeur propre à A (absente de B)
    texte = f"La volatilité vaut {vol_a * 100:.1f} %."
    ctx = fabrique_ctx(tmp_path / "x", handler=_handler_citant(texte, cible=B))
    r = ValuationAgent("allocation").analyse(ctx, [A, B])
    assert [v.actif for v in r.turn.vues] == [A]  # B rejetée : chiffre de A
    assert any(rej.actifs == [B] and "introuvables" in rej.motif for rej in r.rejets)
    ctx2 = fabrique_ctx(tmp_path / "y", handler=_handler_citant(texte, cible=A))
    r2 = ValuationAgent("allocation").analyse(ctx2, [A, B])
    assert {v.actif for v in r2.turn.vues} == {A, B}


def test_valeurs_communes_macro_acceptees_pour_tous_les_actifs(tmp_path):
    ctx0 = fabrique_ctx(tmp_path / "m")
    ev = MacroAgent().evidence(ctx0, [A, B])
    assert all(e.actif is None for e in ev.items if e.valeurs)  # transversales
    commune = next(a.valeur for a in ev.ancres_pour(A) if 0.01 < a.valeur < 1)
    assert [a.valeur for a in ev.ancres_pour(B)] == [a.valeur for a in ev.ancres_pour(A)]
    texte = f"Le régime macro vaut {commune * 100:.1f} %."
    ctx = fabrique_ctx(tmp_path / "x", handler=lambda m, msgs: _tous(m, msgs, texte))
    r = MacroAgent().analyse(ctx, [A, B])
    assert {v.actif for v in r.turn.vues} == {A, B}


def _tous(model, messages, texte):
    out = json.loads(politique_simulee(model, messages))
    for v in out.get("vues", []):
        v["arguments_pour"] = [texte]
    return json.dumps(out, ensure_ascii=False)


def test_valeurs_des_pairs_acceptees_pour_l_actif_concerne_seulement(tmp_path):
    ctx0 = fabrique_ctx(tmp_path / "p")
    vol_a = _valeur_propre(tmp_path / "q", B, A)
    chiffre = f"{vol_a * 100:.1f} %"

    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        systeme = messages[0]["content"]
        if "Agent Valuation" in systeme and "vues" in out:  # le pair : cite SA valeur propre sur A
            for v in out["vues"]:
                if v["actif"] == A:
                    v["arguments_pour"] = [f"La volatilité de A vaut {chiffre}."]
        if "Agent Macro" in systeme and "Tour de débat" in systeme:  # le réviseur : la reprend
            for v in out["vues"]:
                v["arguments_pour"] = [f"Le pair relève {chiffre}."]
        return json.dumps(out, ensure_ascii=False)

    ctx = fabrique_ctx(tmp_path / "x", handler=handler)
    del ctx0
    val = ValuationAgent("allocation").analyse(ctx, [A, B])
    assert {v.actif for v in val.turn.vues} == {A, B}
    res = MacroAgent().revise(ctx, [A, B], [val.turn], {A: 0, B: 0}, tour=1, devil=False)
    assert [v.actif for v in res.turn.vues] == [A]  # reprise acceptée pour A, rejetée pour B
    assert any(r.actifs == [B] and "introuvables" in r.motif for r in res.rejets)


def test_la_valeur_d_un_pair_sur_a_ne_sert_pas_de_justificatif_au_tour_zero(tmp_path):
    ctx = fabrique_ctx(tmp_path, handler=_handler_citant("rendement de 12,7 %"))
    assert MacroAgent().analyse(ctx, [A]).turn.vues == []


def _vues(r):
    return {v.actif for v in r.turn.vues}


def test_une_vue_sur_a_ne_peut_pas_citer_la_source_de_b(tmp_path):
    ctx0 = fabrique_ctx(tmp_path / "s")
    ev = ValuationAgent("allocation").evidence(ctx0, [A, B])
    sid_b = next(e.source_id for e in ev.items if e.actif == B and e.source_id)
    sid_a = next(e.source_id for e in ev.items if e.actif == A and e.source_id)

    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        for v in out.get("vues", []):
            if v["actif"] == A:
                v["source_ids"] = [sid_b]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path / "x", handler=handler)
    r = ValuationAgent("allocation").analyse(ctx, [A, B])
    assert _vues(r) == {B}  # A rejetée : source de B
    assert any(rej.actifs == [A] and "source_id" in rej.motif for rej in r.rejets)
    # sa propre source reste citable
    ctx2 = fabrique_ctx(tmp_path / "y")
    r2 = ValuationAgent("allocation").analyse(ctx2, [A, B])
    assert {s.source_id for v in r2.turn.vues if v.actif == A for s in v.sources} == {sid_a}


def test_les_sources_transversales_sont_citables_pour_tous_les_actifs(tmp_path):
    ctx0 = fabrique_ctx(tmp_path / "m")
    ev = MacroAgent().evidence(ctx0, [A, B])
    transversales = [e.source_id for e in ev.items if e.actif is None and e.source_id]
    assert transversales
    ctx = fabrique_ctx(tmp_path / "x")
    r = MacroAgent().analyse(ctx, [A, B])
    assert _vues(r) == {A, B}
    for v in r.turn.vues:
        assert {s.source_id for s in v.sources} <= set(transversales)


def test_la_source_d_un_pair_est_citable_pour_l_actif_concerne_seulement(tmp_path):
    ctx0 = fabrique_ctx(tmp_path / "s")
    sid_a = next(
        e.source_id
        for e in ValuationAgent("allocation").evidence(ctx0, [A, B]).items
        if e.actif == A and e.source_id
    )

    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        if "Agent Macro" in messages[0]["content"] and "Tour de débat" in messages[0]["content"]:
            for v in out["vues"]:
                v["source_ids"] = [sid_a]  # source du pair Valuation sur A, citée sur A et sur B
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path / "x", handler=handler)
    val = ValuationAgent("allocation").analyse(ctx, [A, B])
    assert _vues(val) == {A, B}
    res = MacroAgent().revise(ctx, [A, B], [val.turn], {A: 0, B: 0}, tour=1, devil=False)
    assert _vues(res) == {A}  # acceptée pour A, rejetée pour B
    assert any(r.actifs == [B] and "source_id" in r.motif for r in res.rejets)
