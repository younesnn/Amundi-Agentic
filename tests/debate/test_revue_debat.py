"""Revue indépendante du débat (L1 §6) : consensus et confiance recalculés à la main, auto-confiance
sans effet, avocat tournant, R_max, gel des unanimes, journal complet, pannes, reprise, K=1,
interchangeabilité LangGraph / boucle."""

from __future__ import annotations

import json
import re

import pytest
from agents_helpers import fabrique_ctx
from debate_helpers import scripte

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.debate import consensus as cs
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.debate import devil as dv
from amundi_agentic.llm.types import ProviderError

CLASSES = ["actions_etats_unis", "souverain_euro", "or"]
MACRO = "Agent Macro"
VALO = "Agent Valuation / Momentum (allocation)"
S = load_settings()


def lancer(
    tmp_path, script=None, *, overrides=None, handler=None, assets=CLASSES, live=False, **kw
):
    ctx = fabrique_ctx(
        tmp_path, handler=handler or scripte(script), settings_overrides=overrides, **kw
    )
    votants = construire_votants(ctx, "allocation", live=live)
    esg = EsgAgent().evaluer(ctx, "allocation", assets)
    res = run_debate(ctx, "allocation", assets, votants, Coordinator(), esg, risk_agent=RiskAgent())
    return ctx, res


# --------------------------------------------------------------------------- paramètres de L1
def test_les_parametres_du_yaml_sont_ceux_de_l1_6_4():
    c = S.confidence
    assert (c.c_max, c.c_min) == (0.8, 0.05)
    assert dict(c.g) == {"unanime": 1.0, "consensus": 0.75, "contestee": 0.4}
    assert dict(c.h) == {"aucune": 1.0, "moderee": 0.8, "elevee": 0.6}
    assert c.rho_par_tour == 0.1
    assert (S.consensus.ecart_consensus_large, S.consensus.ecart_contestee_min) == (1, 2)
    assert S.consensus.borne_contestee == 1 and S.debate.r_max == 2


# 5 cas recalculés à la main : c = min(c_max, max(c_min, c_max . A . g . rho . h))
# niveaux, n*, statut, tours, alerte -> A, c attendu
CAS_MAIN = [
    ((1, 1, 1), 1, "unanime", 0, "aucune", 1.0, 0.8),  # 0,8 x 1 x 1 x 1 x 1
    ((-2, 0, 2), 0, "contestee", 2, "aucune", 1 - 4 / 12, 0.8 * (2 / 3) * 0.4 * 0.8),  # 0,1707
    ((1, 1, 2), 1, "consensus", 2, "moderee", 1 - 1 / 12, 0.8 * (11 / 12) * 0.75 * 0.8 * 0.8),
    ((1, 2), 1, "consensus", 1, "aucune", 1 - 1 / 8, 0.8 * (7 / 8) * 0.75 * 0.9),  # K = 2
    ((-2, 2), 0, "contestee", 9, "elevee", 0.5, 0.05),  # plancher c_min : brut 0,0096
]


@pytest.mark.parametrize("niveaux,n_final,statut,tours,alerte,a,attendu", CAS_MAIN)
def test_confiance_recalculee_a_la_main(niveaux, n_final, statut, tours, alerte, a, attendu):
    assert cs.accord(niveaux, n_final) == pytest.approx(a)
    assert cs.confiance(a, statut, tours, alerte, S.confidence) == pytest.approx(attendu)
    assert S.confidence.c_min <= attendu <= S.confidence.c_max


def test_exemple_de_l1_vue_contestee_apres_deux_tours():
    # L1 : A = 0,75, contestee, 2 tours, h = 1 : 0,8 x 0,75 x 0,4 x 0,8 = 0,192
    assert cs.confiance(0.75, "contestee", 2, "aucune", S.confidence) == pytest.approx(0.192)


def test_confiance_jamais_au_dela_de_c_max_ni_sous_c_min():
    for a in (0.0, 0.3, 1.0, 5.0):
        for statut in ("unanime", "consensus", "contestee"):
            for tours in (0, 1, 2, 20):
                for alerte in ("aucune", "moderee", "elevee"):
                    c = cs.confiance(a, statut, tours, alerte, S.confidence)
                    assert 0.05 <= c <= 0.8


@pytest.mark.parametrize(
    "niveaux,statut",
    [
        ((1, 1, 1), "unanime"),
        ((0, 1), "consensus"),
        ((-1, 0, 0), "consensus"),
        ((-1, 1), "contestee"),  # écart 2 même autour de zéro
        ((0, 2), "contestee"),
        ((-2, 2), "contestee"),
        ((-2, -1, 1), "contestee"),
    ],
)
def test_statut_selon_l_ecart(niveaux, statut):
    assert cs.statut_apres_rmax(cs.evaluer(niveaux), S.consensus) == statut


@pytest.mark.parametrize(
    "niveaux,mediane",
    [((-2, -1), -1), ((-1, 2), 0), ((1, 2), 1), ((-2, 1), 0), ((0, 1, 2), 1), ((-2, 0, 1), 0)],
)
def test_mediane_de_deux_niveaux_arrondie_vers_zero(niveaux, mediane):
    assert cs.mediane_vers_zero(niveaux) == mediane


def test_borne_des_vues_contestees():
    assert [cs.borner(n, -2, 2, 1) for n in (-2, -1, 0, 1, 2)] == [-1, -1, 0, 1, 1]
    assert cs.borner(2, -2, -1, 1) == -1  # niveau choisi hors des votes : d'abord dans [min, max]


# --------------------------------------------------------------------------- consensus en Python
def test_l_auto_confiance_des_agents_n_entre_pas_dans_la_confiance_finale(tmp_path):
    def avec_confiance(valeur):
        base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

        def handler(model, messages):
            out = json.loads(base(model, messages))
            for v in out.get("vues", []):
                v["confiance"] = valeur
            return json.dumps(out)

        return handler

    sortie = {}
    for c in (0.0, 0.1, 0.5, 1.0):
        _, res = lancer(tmp_path / f"c{c}", handler=avec_confiance(c))
        sortie[c] = [
            (o.actif, o.statut, o.niveau_final, o.confiance_finale) for o in res.log.resultats
        ]
    assert len({json.dumps(v) for v in sortie.values()}) == 1
    # l'auto-confiance est journalisée dans les vues du journal des tours
    _, res = lancer(tmp_path / "j", handler=avec_confiance(0.37))
    vues = [v for r in res.log.tours for t in r.tours_agents for v in t.vues]
    assert vues and all(v.confiance == 0.37 for v in vues)
    assert all(v.confiance != 0.37 for v in res.vues_finales)  # la vue finale porte la règle 6.4


def test_le_llm_ne_peut_pas_declarer_un_consensus_ni_terminer_le_debat(tmp_path):
    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

    def handler(model, messages):
        out = json.loads(base(model, messages))
        out["TERMINATE"] = True
        out["consensus"] = "unanime"
        out["statut"] = "unanime"
        out["niveau_final"] = 2
        for v in out.get("vues", []):
            v["statut"] = "unanime"
        return json.dumps(out)

    ctx, res = lancer(tmp_path, handler=handler)
    assert [t.numero for t in res.log.tours] == list(range(ctx.settings.debate.r_max + 1))
    assert {o.statut for o in res.log.resultats} == {"contestee"}


def test_les_niveaux_du_journal_viennent_des_vues_pas_du_texte(tmp_path):
    def handler(model, messages):
        out = json.loads(
            scripte(lambda role, tour, actif: 0 if role == MACRO else 1)(model, messages)
        )
        for v in out.get("vues", []):
            v["arguments_pour"] = ["Tout le monde est unanimement positif (+2)."]
        return json.dumps(out)

    _, res = lancer(tmp_path, handler=handler)
    assert {o.statut for o in res.log.resultats} == {"consensus"}


# --------------------------------------------------------------------------- vue contestée
def test_vue_contestee_bornee_a_un_et_confiance_reduite(tmp_path):
    def handler(model, messages):
        if "Coordinateur : arbitrage" in messages[0]["content"]:
            actifs = re.findall(r"actif=(\S+) min", messages[1]["content"])
            return json.dumps(
                {
                    "arbitrages": [
                        {"actif": a, "niveau": -2, "justification": "baisse"} for a in actifs
                    ]
                }
            )
        return scripte(lambda role, tour, actif: -2 if role == MACRO else 2)(model, messages)

    ctx, res = lancer(tmp_path, handler=handler)
    for o in res.log.resultats:
        assert o.statut == "contestee" and o.niveau_final == -1  # -2 choisi, borné à -1
        assert o.confiance_finale <= 0.8 * 0.4  # g(contestee) = 0,4
    for v in res.vues_finales:
        assert v.statut == "contestee" and v.direction.n == -1 and v.confiance <= 0.32


def test_aucun_arbitrage_sans_vue_contestee(tmp_path):
    _, res = lancer(tmp_path, lambda role, tour, actif: 1)
    assert [a.nature for a in res.log.appels].count("arbitrage") == 0


# --------------------------------------------------------------------------- avocat du diable
@pytest.mark.parametrize("graine", [0, 1, 2, 3, 4])
def test_avocat_tournant_deterministe_son_vote_compte_sans_appel_supplementaire(tmp_path, graine):
    ctx, res = lancer(
        tmp_path,
        lambda role, tour, actif: -1 if role == MACRO else 1,
        overrides={"debate": {"graine_rotation": graine, "r_max": 3}},
        live=True,
    )
    votants = ["macro", "valuation", "sentiment"]
    tours = res.log.tours[1:]
    assert len(tours) == 3
    attendus = [dv.designer(votants, r, ctx.t, "allocation", graine) for r in (1, 2, 3)]
    assert [t.avocat_du_diable for t in tours] == attendus
    assert len(set(attendus)) == 3  # tournant : trois votants, trois tours, trois avocats distincts
    for t in tours:
        assert len(t.tours_agents) == 3  # aucun appel supplémentaire : un tour par votant
        avocat = next(a for a in t.tours_agents if a.agent == t.avocat_du_diable)
        assert avocat.role == "avocat_du_diable" and avocat.objection and avocat.vues
        assert all(
            a.role == "normal" and a.objection is None for a in t.tours_agents if a is not avocat
        )
    # un appel de révision par votant et par tour, pas un de plus
    revisions = [a for a in res.log.appels if a.nature == "revision"]
    assert len(revisions) == 3 * 3


def test_avocat_votes_comptent_dans_le_consensus(tmp_path):
    """Si l'avocat (seul à s'écarter) déplace son vote, le niveau final en tient compte."""
    ctx, res = lancer(
        tmp_path,
        lambda role, tour, actif: 1 if role != MACRO else (0 if tour == 0 else 1),
        overrides={"debate": {"graine_rotation": 0}},
    )
    assert {o.statut for o in res.log.resultats} == {
        "unanime"
    }  # Macro se rallie, vote pris en compte


def test_la_designation_ne_depend_que_de_date_niveau_graine():
    from datetime import date

    a = dv.designer(["x", "y", "z"], 1, date(2024, 2, 1), "allocation", 0)
    assert a == dv.designer(["x", "y", "z"], 1, date(2024, 2, 1), "allocation", 0)
    with pytest.raises(ValueError):
        dv.designer(["x"], 0, date(2024, 2, 1), "allocation", 0)
    designes = {
        dv.designer(["x", "y", "z"], 1, date(2024, 2, d), "allocation", 0) for d in range(1, 29)
    }
    assert len(designes) > 1  # h varie avec la date


# --------------------------------------------------------------------------- R_max, gel
@pytest.mark.parametrize("r_max", [0, 1, 2, 3])
def test_arret_a_r_max(tmp_path, r_max):
    ctx, res = lancer(
        tmp_path,
        lambda role, tour, actif: -1 if role == MACRO else 1,
        overrides={"debate": {"r_max": r_max}},
    )
    assert [t.numero for t in res.log.tours] == list(range(r_max + 1))
    assert all(o.tours_utilises == r_max for o in res.log.resultats)
    assert {o.statut for o in res.log.resultats} == {"contestee"}


def test_actif_unanime_fige_n_est_plus_revise(tmp_path):
    def script(role, tour, actif):
        if actif == "or":
            return 1  # unanime dès le tour 0
        return -1 if role == MACRO else 1

    ctx, res = lancer(tmp_path, script)
    sortie_or = next(o for o in res.log.resultats if o.actif == "or")
    assert sortie_or.statut == "unanime" and sortie_or.tours_utilises == 0
    for t in res.log.tours[1:]:
        for at in t.tours_agents:
            assert all(v.actif != "or" for v in at.vues)
    for a in res.log.appels:
        if a.nature == "revision":
            m = re.search(r"Actifs à analyser : (\[.*?\])", a.messages[1]["content"])
            assert "or" not in json.loads(m.group(1))


def test_un_actif_qui_devient_unanime_au_tour_un_n_est_plus_revise_au_tour_deux(tmp_path):
    def script(role, tour, actif):
        if actif == "or":
            return 1 if role != MACRO else (0 if tour == 0 else 1)
        return -1 if role == MACRO else 1

    ctx, res = lancer(tmp_path, script)
    o = next(x for x in res.log.resultats if x.actif == "or")
    assert o.statut == "unanime" and o.tours_utilises == 1
    assert all(v.actif != "or" for at in res.log.tours[2].tours_agents for v in at.vues)


# --------------------------------------------------------------------------- journal complet
def test_journal_complet_prompts_reponses_sources_durees_tokens_rejets(tmp_path):
    ctx, res = lancer(tmp_path, lambda role, tour, actif: -1 if role == MACRO else 1)
    log = res.log
    assert log.appels and log.duree_s >= 0 and log.tokens_entree > 0 and log.tokens_sortie > 0
    for a in log.appels:
        assert a.messages and a.messages[0]["role"] == "system" and a.reponse
        assert re.fullmatch(r"[0-9a-f]{64}", a.prompt_sha256) and a.prompt_id and a.prompt_version
        r = a.record
        assert r.modele_servi and r.cle_cache and r.tokens_entree >= 0 and r.mode == "interactif"
    natures = {a.nature for a in log.appels}
    assert {"analyse", "revision", "rapport", "arbitrage"} <= natures
    assert log.config.r_max == S.debate.r_max and log.config.parametres_confiance["c_max"] == 0.8
    vues = [v for r in log.tours for t in r.tours_agents for v in t.vues]
    assert vues and all(v.sources and v.arguments_pour and v.arguments_contre for v in vues)
    assert all(t.appels_outils for r in log.tours[:1] for t in r.tours_agents)
    assert log.rapport_coordinateur and log.votants == ["macro", "valuation"]
    assert log.risque is not None and sorted(log.actifs) == sorted(CLASSES)
    assert set(log.prompt_sha256) >= {"macro", "regles_communes"} or log.prompt_sha256
    # le journal se sérialise et se relit à l'identique
    from amundi_agentic.schemas import DebateLog

    assert DebateLog.model_validate_json(log.model_dump_json()) == log


def test_les_rejets_sont_journalises(tmp_path):
    def handler(model, messages):
        if "Agent Valuation" in messages[0]["content"] and "vues" in politique_simulee(
            model, messages
        ):
            return "pas du json"
        return scripte(lambda role, tour, actif: 1)(model, messages)

    ctx, res = lancer(tmp_path, handler=handler)
    assert any(r.agent == "valuation" for r in res.log.rejets)
    assert res.log.votants == ["macro"]


# --------------------------------------------------------------------------- arbitrage groupé
def test_arbitrage_un_seul_appel_meme_avec_cinq_actifs_contestes(tmp_path):
    actifs = ["actions_etats_unis", "souverain_euro", "or", "matieres_premieres", "immobilier_cote"]
    from amundi_agentic.agents.providers import SyntheticData

    univers = SyntheticData(__import__("datetime").date(2024, 2, 1)).classes
    actifs = [a for a in actifs if a in univers][:5]
    ctx, res = lancer(tmp_path, lambda role, tour, actif: -2 if role == MACRO else 2, assets=actifs)
    assert [a.nature for a in res.log.appels].count("arbitrage") == 1
    assert {o.statut for o in res.log.resultats} == {"contestee"}


# --------------------------------------------------------------------------- cas K = 1
def test_k1_un_seul_agent_valide_donne_unanime_par_construction_avec_confiance_elevee(tmp_path):
    """Constat : si les autres agents sont rejetés (ou en panne), la vue d'un seul agent est
    `unanime` et reçoit c = c_max . g(unanime) . h : jusqu'à 0,8, comme trois agents d'accord.
    Dangereux : une seule voix, non contredite, sans débat. Règle proposée (non codée) : exiger
    K_valides >= 2, sinon plafonner la confiance (g effectif = g(consensus)) ou signaler le statut
    `voix_unique` et ne pas le transmettre à Black-Litterman sans validation du gérant."""

    def handler(model, messages):
        systeme = messages[0]["content"]
        if "Agent Valuation" in systeme and "Coordinateur" not in systeme:
            return "pas du json"  # Valuation rejetée à chaque tour
        return scripte(lambda role, tour, actif: 1)(model, messages)

    ctx, res = lancer(tmp_path, handler=handler)
    assert res.log.votants == ["macro"]
    for o in res.log.resultats:
        assert o.statut == "unanime" and o.tours_utilises == 0
        if o.alerte_risque == "aucune":
            assert o.confiance_finale == pytest.approx(0.8)  # même confiance que 3 votants d'accord
    assert {o.confiance_finale for o in res.log.resultats if o.alerte_risque == "aucune"} <= {0.8}


def test_aucun_agent_valide_aucune_decision_et_aucune_vue(tmp_path):
    ctx, res = lancer(tmp_path, handler=lambda m, msgs: "pas du json")
    assert res.vues_finales == [] and res.log.resultats == []
    assert set(res.log.sans_decision) == set(CLASSES)


# --------------------------------------------------------------------------- pannes
@pytest.mark.parametrize("kind", ["unavailable", "timeout"])
def test_panne_pendant_la_collaboration_remonte_sans_vue_inventee(tmp_path, kind):
    def handler(model, messages):
        if "Agent Valuation" in messages[0]["content"]:
            raise ProviderError(kind, "panne simulée")
        return scripte(lambda role, tour, actif: 1)(model, messages)

    with pytest.raises(ProviderError):
        lancer(tmp_path, handler=handler)


def test_quota_epuise_pendant_la_collaboration_remonte(tmp_path):
    from amundi_agentic.llm.types import QuotaEpuise

    def handler(model, messages):
        raise ProviderError("quota", "429 simulé", 429)

    with pytest.raises(QuotaEpuise):
        lancer(tmp_path, handler=handler)


@pytest.mark.parametrize("kind", ["unavailable", "timeout"])
def test_panne_pendant_la_revision_conserve_le_vote_et_continue(tmp_path, kind):
    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

    def handler(model, messages):
        if (
            "Tour de débat" in messages[0]["content"]
            and "Agent Valuation" in messages[0]["content"]
        ):
            raise ProviderError(kind, "panne simulée")
        return base(model, messages)

    ctx, res = lancer(tmp_path, handler=handler)
    assert any("panne du fournisseur" in r.motif and r.agent == "valuation" for r in res.log.rejets)
    assert {o.statut for o in res.log.resultats} == {"contestee"}
    assert res.log.tours[-1].niveaux["or"]["valuation"] == 1  # vote du tour 0 conservé


def test_quota_epuise_pendant_la_revision_arrete_le_debat(tmp_path):
    from amundi_agentic.llm.types import QuotaEpuise

    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

    def handler(model, messages):
        if "Tour de débat" in messages[0]["content"]:
            raise ProviderError("quota", "429", 429)
        return base(model, messages)

    with pytest.raises(QuotaEpuise):
        lancer(tmp_path, handler=handler)


def test_json_invalide_pendant_la_revision_conserve_le_vote_precedent(tmp_path):
    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

    def handler(model, messages):
        if "Tour de débat" in messages[0]["content"] and "Agent Macro" in messages[0]["content"]:
            return "{pas du json"
        return base(model, messages)

    ctx, res = lancer(tmp_path, handler=handler)
    assert any(r.agent == "macro" and r.tour >= 1 for r in res.log.rejets)
    assert {o.statut for o in res.log.resultats} == {"contestee"}
    assert all(t.niveaux["or"]["macro"] == -1 for t in res.log.tours)


# --------------------------------------------------------------------------- reprise sur interruption
def test_interruption_puis_reprise_sans_nouvel_appel_pour_les_requetes_deja_faites(tmp_path):
    from amundi_agentic.debate.run import executer

    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

    def faire(chemin, handler):
        ctx = fabrique_ctx(chemin, handler=handler)
        return ctx, executer(ctx, classes=CLASSES, titres=[], live=False)

    ctx_ref, sortie_ref = faire(tmp_path / "ref", base)
    total = len(ctx_ref.llm.mock.chat_calls)
    assert total > 6 and not sortie_ref.interrompu

    n = {"k": 0}

    def tombe_apres_5(model, messages):
        n["k"] += 1
        if n["k"] > 5:
            raise ProviderError("quota", "429 simulé", 429)
        return base(model, messages)

    ctx1, s1 = faire(tmp_path / "run", tombe_apres_5)
    assert s1.interrompu and "QuotaEpuise" in s1.interrompu
    faits = [c for c in ctx1.llm.records if not c.cache_hit and c.erreur is None]
    assert len(faits) == 5

    ctx2, s2 = faire(tmp_path / "run", base)  # même cache : reprise
    assert not s2.interrompu
    assert len(ctx2.llm.mock.chat_calls) == total - 5  # aucun appel refait
    assert ctx2.llm.usage()["cache_hits"] >= 5
    meme = lambda s: [  # noqa: E731
        (o.actif, o.statut, o.niveau_final, round(o.confiance_finale, 9))
        for d in s.debats
        for o in d.log.resultats
    ]
    assert meme(s2) == meme(sortie_ref)


# --------------------------------------------------------------------------- un débat par titre
def test_un_debat_par_titre_sans_fuite_d_etat_entre_titres(tmp_path):
    from amundi_agentic.debate.run import executer

    def script(role, tour, actif):
        if actif == "AAA":
            return 2
        if actif == "BBB":
            return -2 if "Fundamental" in role else 2
        return 0

    def sortie(titres, chemin):
        ctx = fabrique_ctx(chemin, handler=scripte(script), stocks=("AAA", "BBB", "CCC"))
        return executer(ctx, classes=[], titres=titres, live=False)

    seul = sortie(["BBB"], tmp_path / "seul")
    tous = sortie(["AAA", "BBB", "CCC"], tmp_path / "tous")
    assert len(tous.debats) == 3
    ids = [d.log.debate_id for d in tous.debats]
    assert len(set(ids)) == 3 and all(
        t in i for t, i in zip(("AAA", "BBB", "CCC"), ids, strict=True)
    )
    b_seul = next(o for d in seul.debats for o in d.log.resultats)
    b_tous = next(o for d in tous.debats for o in d.log.resultats if o.actif == "BBB")
    assert (b_seul.statut, b_seul.niveau_final, round(b_seul.confiance_finale, 9)) == (
        b_tous.statut,
        b_tous.niveau_final,
        round(b_tous.confiance_finale, 9),
    )
    for d in tous.debats:
        assert d.log.actifs in (["AAA"], ["BBB"], ["CCC"])
        assert all(v.actif == d.log.actifs[0] for v in d.vues_finales)


# --------------------------------------------------------------------------- orchestrateurs
PROFILS = ["prudent", "equilibre", "dynamique"]


def _empreinte(res):
    log = res.log
    return {
        "trace": res.trace_graphe,
        "resultats": [o.model_dump() for o in log.resultats],
        "niveaux": [t.niveaux for t in log.tours],
        "avocats": [t.avocat_du_diable for t in log.tours],
        "statuts": [t.statut_apres_tour for t in log.tours],
        "rapport": log.rapport_coordinateur,
        "vues": [
            (v.actif, v.direction.value, v.statut, round(v.confiance, 9)) for v in res.vues_finales
        ],
        "appels": [(a.agent, a.tour, a.nature, a.prompt_sha256, a.reponse) for a in log.appels],
        "rejets": [r.model_dump() for r in log.rejets],
    }


GRILLE = [(g, p) for g in range(5) for p in PROFILS]
CI = [(0, "prudent"), (1, "equilibre"), (2, "dynamique"), (3, "equilibre"), (4, "prudent")]


@pytest.mark.parametrize(
    "graine,profil",
    [pytest.param(g, p, marks=[] if (g, p) in CI else pytest.mark.slow) for g, p in GRILLE],
)
def test_langgraph_et_boucle_donnent_exactement_le_meme_debat(tmp_path, graine, profil):
    def script(role, tour, actif):
        return 0 if role == MACRO else (1 if tour == 0 else 0 if tour == 1 else 1)

    empreintes = {}
    for nom in ("langgraph", "boucle"):
        _, res = lancer(
            tmp_path / nom,
            script,
            overrides={"debate": {"orchestrateur": nom, "graine_rotation": graine, "r_max": 3}},
            profil=profil,
            live=True,
        )
        empreintes[nom] = _empreinte(res)
    assert empreintes["langgraph"] == empreintes["boucle"]


def test_langgraph_et_boucle_meme_resultat_sur_un_debat_conteste_et_arbitre(tmp_path):
    empreintes = {}
    for nom in ("langgraph", "boucle"):
        _, res = lancer(
            tmp_path / nom,
            lambda role, tour, actif: -2 if role == MACRO else 2,
            overrides={"debate": {"orchestrateur": nom}},
        )
        empreintes[nom] = _empreinte(res)
    assert empreintes["langgraph"] == empreintes["boucle"]


def test_les_deux_orchestrateurs_sont_les_seules_valeurs_acceptees():
    from amundi_agentic.agents.settings import SettingsError

    with pytest.raises(SettingsError):
        load_settings(overrides={"debate": {"orchestrateur": "autre"}})


def test_boucle_python_n_importe_pas_langgraph(tmp_path, monkeypatch):
    import sys

    for nom in [m for m in sys.modules if m.startswith("langgraph")]:
        monkeypatch.delitem(sys.modules, nom)
    monkeypatch.setitem(sys.modules, "langgraph", None)  # tout import échouerait
    _, res = lancer(
        tmp_path, lambda role, tour, actif: 1, overrides={"debate": {"orchestrateur": "boucle"}}
    )
    assert res.vues_finales


# --------------------------------------------------------------------------- modèle servi (évaluation)
def _ctx_evaluation(tmp_path, handler):
    from amundi_agentic.llm import MockLLMClient, load_config

    ctx = fabrique_ctx(tmp_path, handler=handler)
    cfg = load_config()
    ctx.llm = MockLLMClient(
        cfg,
        mode="evaluation",
        profile="prod",
        handler=handler,
        cache_dir=tmp_path / "cache_eval",
        quota_journal=tmp_path / "q_eval.json",
        run_dir=tmp_path / "run_eval",
        run_id="eval",
    )
    return ctx, cfg


def test_changement_de_modele_servi_en_plein_debat_arrete_l_execution(tmp_path):
    from amundi_agentic.debate.run import executer
    from amundi_agentic.llm.types import ModeleServiChange

    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)
    etat = {"n": 0, "ctx": None, "cfg": None}

    def handler(model, messages):
        etat["n"] += 1
        if etat["n"] == 6:  # dérive silencieuse du fournisseur au 6e appel
            etat["ctx"].llm.mock.set_served(model, "version-derivee")
        return base(model, messages)

    ctx, cfg = _ctx_evaluation(tmp_path, handler)
    etat["ctx"] = ctx
    with pytest.raises(ModeleServiChange):
        executer(ctx, classes=CLASSES, titres=[], live=False)
    assert etat["n"] >= 6
    erreurs = [r for r in ctx.llm.records if r.erreur and "modele_servi_change" in r.erreur]
    assert erreurs and erreurs[0].modele_servi == "version-derivee"  # l'appel fautif est journalisé


def test_en_evaluation_le_modele_servi_est_fige_par_niveau_pendant_tout_le_debat(tmp_path):
    from amundi_agentic.debate.run import executer

    ctx, cfg = _ctx_evaluation(
        tmp_path, scripte(lambda role, tour, actif: -1 if role == MACRO else 1)
    )
    sortie = executer(ctx, classes=CLASSES, titres=[], live=False)
    assert not sortie.interrompu
    figes = ctx.llm.modeles_servis_figes
    assert figes and set(figes) <= {"main", "light", "embed"}
    servis = {r.modele_servi for r in ctx.llm.records if r.erreur is None}
    assert len(servis) <= len(figes)  # un seul modèle servi par niveau figé
    assert not any(r.relais_utilise for r in ctx.llm.records)


def test_interruption_clavier_n_est_pas_avalee_par_le_debat(tmp_path):
    def handler(model, messages):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        lancer(tmp_path, handler=handler)
