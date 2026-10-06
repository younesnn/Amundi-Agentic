"""Débat (L1 §6) avec réponses scriptées du LLM simulé : consensus en Python, vue contestée,
avocat du diable tournant, arrêt à R_max, journal complet, veto ESG."""

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
from amundi_agentic.debate import consensus as cs
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.schemas import DebateLog

CLASSES = ["actions_etats_unis", "souverain_euro", "or"]
MACRO = "Agent Macro"
VALO = "Agent Valuation / Momentum (allocation)"


def lancer(tmp_path, script, *, overrides=None, handler=None, assets=CLASSES, **kw):
    ctx = fabrique_ctx(
        tmp_path, handler=handler or scripte(script), settings_overrides=overrides, **kw
    )
    votants = construire_votants(ctx, "allocation", live=False)
    esg = EsgAgent().evaluer(ctx, "allocation", assets)
    res = run_debate(ctx, "allocation", assets, votants, Coordinator(), esg, risk_agent=RiskAgent())
    return ctx, res


def test_sentiment_ne_vote_pas_en_backtest(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    assert [a.name for a in construire_votants(ctx, "allocation", live=False)] == [
        "macro",
        "valuation",
    ]
    assert [a.name for a in construire_votants(ctx, "allocation", live=True)] == [
        "macro",
        "valuation",
        "sentiment",
    ]
    assert [a.name for a in construire_votants(ctx, "titre", live=True)] == [
        "fundamental",
        "sentiment",
        "valuation",
    ]


def test_unanimite_au_tour_zero_arrete_le_debat(tmp_path):
    ctx, res = lancer(tmp_path, lambda role, tour, actif: 1)
    assert res.trace_graphe == ["collaboration", "finaliser"]
    assert [t.numero for t in res.log.tours] == [0]
    cfg = ctx.settings.confidence
    for o in res.log.resultats:
        assert o.statut == "unanime" and o.niveau_final == 1 and o.tours_utilises == 0
        assert o.accord_A == 1.0
        attendu = max(
            cfg.c_min, min(cfg.c_max, cfg.c_max * cfg.g["unanime"] * cfg.h[o.alerte_risque])
        )
        assert o.confiance_finale == pytest.approx(attendu)
    # appels : macro 1 + valuation 1 + risque (commentaire) 1 + rapport 1
    assert len(res.log.appels) == 4


def test_consensus_apres_rmax_mediane_vers_zero(tmp_path):
    def script(role, tour, actif):
        return 0 if role == MACRO else 1  # écart d'un cran qui ne se résorbe jamais

    ctx, res = lancer(tmp_path, script)
    r_max = ctx.settings.debate.r_max
    assert [t.numero for t in res.log.tours] == list(range(r_max + 1))
    for o in res.log.resultats:
        assert o.statut == "consensus" and o.niveau_final == 0  # médiane de (0, 1) vers 0
        assert o.tours_utilises == r_max


def test_vue_contestee_confiance_reduite_et_niveau_borne(tmp_path):
    def script(role, tour, actif):
        return -2 if role == MACRO else 2

    def handler_arbitre_extreme(model, messages):
        systeme = messages[0]["content"]
        if "Coordinateur : arbitrage" in systeme:
            actifs = re.findall(r"actif=(\S+) min", messages[1]["content"])
            return json.dumps(
                {
                    "arbitrages": [
                        {"actif": a, "niveau": 2, "justification": "tranche en faveur de la hausse"}
                        for a in actifs
                    ]
                }
            )
        return scripte(script)(model, messages)

    ctx, res = lancer(tmp_path, script, handler=handler_arbitre_extreme)
    cfg = ctx.settings
    for o in res.log.resultats:
        assert o.statut == "contestee"
        assert -cfg.consensus.borne_contestee <= o.niveau_final <= cfg.consensus.borne_contestee
        assert o.niveau_final == 1  # +2 choisi par le coordinateur, borné à +1
        assert o.arbitrage and "hausse" in o.arbitrage
        # confiance réduite : g(contestee) = 0,4 < g(consensus)
        assert o.confiance_finale <= cfg.confidence.c_max * cfg.confidence.g["contestee"]
    for v in res.vues_finales:
        assert v.statut == "contestee" and abs(v.direction.n) <= 1


def test_arret_des_que_unanime_au_tour_un(tmp_path):
    def script(role, tour, actif):
        if role == MACRO:
            return 0
        return 1 if tour == 0 else 0  # Valuation se rallie au tour 1

    ctx, res = lancer(tmp_path, script)
    assert [t.numero for t in res.log.tours] == [0, 1]
    for o in res.log.resultats:
        assert o.statut == "unanime" and o.tours_utilises == 1
    assert res.log.tours[1].statut_apres_tour == dict.fromkeys(CLASSES, "unanime")


def test_nombre_maximal_de_tours_respecte(tmp_path):
    for r_max in (0, 1, 3):
        ctx, res = lancer(
            tmp_path / f"r{r_max}",
            lambda role, tour, actif: -1 if role == MACRO else 1,
            overrides={"debate": {"r_max": r_max}},
        )
        assert len(res.log.tours) == r_max + 1
        assert res.log.config.r_max == r_max
        # R_max appels de révision par votant au plus
        revisions = [a for a in res.log.appels if a.nature == "revision"]
        assert len(revisions) == 2 * r_max


def test_avocat_du_diable_tourne_et_son_vote_compte(tmp_path):
    ctx, res = lancer(
        tmp_path,
        lambda role, tour, actif: -1 if role == MACRO else 1,
        overrides={"debate": {"r_max": 2}},
    )
    avocats = [t.avocat_du_diable for t in res.log.tours[1:]]
    assert len(avocats) == 2 and avocats[0] != avocats[1] and set(avocats) == {"macro", "valuation"}
    for tour in res.log.tours[1:]:
        for at in tour.tours_agents:
            if at.agent == tour.avocat_du_diable:
                assert at.role == "avocat_du_diable" and at.objection
            else:
                assert at.role == "normal" and at.objection is None
            assert at.vues  # son vote compte : chaque agent, avocat compris, vote
    # aucun appel supplémentaire pour l'avocat : 2 révisions par tour
    assert [a.nature for a in res.log.appels].count("revision") == 4


def test_avocat_sans_objection_est_signale_pas_ignore(tmp_path):
    ctx, res = lancer(
        tmp_path,
        lambda role, tour, actif: -1 if role == MACRO else 1,
        handler=scripte(lambda role, tour, actif: -1 if role == MACRO else 1, objection_ok=False),
        overrides={"debate": {"r_max": 1}},
    )
    assert any("objection" in r.motif for r in res.log.rejets)
    tour1 = res.log.tours[1]
    assert all(t.role == "normal" for t in tour1.tours_agents)  # pas d'objection : pas de rôle


def test_journal_de_debat_complet(tmp_path):
    ctx, res = lancer(tmp_path, lambda role, tour, actif: -1 if role == MACRO else 1)
    log = res.log
    relu = DebateLog.model_validate_json(log.model_dump_json())
    assert relu == log
    json.loads(log.model_dump_json())  # JSON valide
    assert log.appels and all(a.messages and a.reponse for a in log.appels)
    assert all(
        len(a.prompt_sha256) == 64 and a.record.prompt_sha256 == a.prompt_sha256 for a in log.appels
    )
    assert log.tokens_entree > 0 and log.tokens_sortie > 0 and log.duree_s >= 0
    assert log.rapport_coordinateur and log.risque is not None and log.esg
    assert log.votants == ["macro", "valuation"]
    assert log.config.r_max == ctx.settings.debate.r_max
    for t in log.tours:
        for at in t.tours_agents:
            assert at.appels_outils  # chaque tour d'agent porte ses ToolCall
    assert log.prompt_sha256  # hash de chaque prompt utilisé


def test_consensus_calcule_en_python_pas_par_le_llm(tmp_path):
    # le LLM ajoute des champs « consensus » / « TERMINATE » : sans effet sur le résultat
    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

    def handler(model, messages):
        out = json.loads(base(model, messages))
        out.update({"consensus": True, "statut": "unanime", "terminate": "TERMINATE"})
        return json.dumps(out)

    ctx, res = lancer(tmp_path, None, handler=handler)
    assert {o.statut for o in res.log.resultats} == {"contestee"}


def test_actif_sous_veto_n_entre_jamais_dans_le_debat(tmp_path):
    ctx = fabrique_ctx(tmp_path, esg_exclus=("BBB",), handler=scripte(lambda r, t, a: 1))
    esg = EsgAgent().evaluer(ctx, "titre", ["AAA", "BBB"])
    assert esg["BBB"].veto and not esg["AAA"].veto
    from amundi_agentic.agents.valuation import ValuationAgent

    res = run_debate(ctx, "titre", ["AAA", "BBB"], [ValuationAgent("titre")], Coordinator(), esg)
    assert res.exclus_esg == ["BBB"]
    assert [v.actif for v in res.vues_finales] == ["AAA"]
    # seul le rapport du coordinateur nomme l'actif exclu (transparence) ; aucun analyste ne le voit
    assert all(
        "BBB" not in m["content"]
        for a in res.log.appels
        if a.agent != "coordinateur"
        for m in a.messages
    )
    assert [o.actif for o in res.log.resultats] == ["AAA"]


def test_vue_non_ancree_rejetee_et_l_agent_s_abstient(tmp_path):
    def inventeur(model, messages):
        out = json.loads(politique_simulee(model, messages))
        if "Agent Macro" in messages[0]["content"]:
            for v in out["vues"]:
                v["arguments_pour"] = ["Le rendement annualisé atteint 123,45 % selon l'outil."]
        return json.dumps(out)

    ctx, res = lancer(tmp_path, None, handler=inventeur)
    assert res.log.votants == ["valuation"]  # Macro n'a produit aucune vue acceptée
    assert any(r.agent == "macro" and "123,45" in r.motif for r in res.log.rejets)
    # nouvelles demandes bornées : 1 + max_retries appels de Macro au tour 0
    n_macro = [a for a in res.log.appels if a.agent == "macro"]
    assert len(n_macro) == ctx.settings.grounding.max_retries + 1


def test_confiance_formule_de_l1(tmp_path):
    cfg = fabrique_ctx(tmp_path).settings.confidence
    # exemple de L1 §6.4 : contestée après 2 tours, A = 0,75, sans alerte
    c = cs.confiance(0.75, "contestee", 2, "aucune", cfg)
    assert c == pytest.approx(cfg.c_max * 0.75 * cfg.g["contestee"] * (1 - 2 * cfg.rho_par_tour))
    assert cs.confiance(1.0, "unanime", 0, "aucune", cfg) == cfg.c_max
    assert cs.confiance(0.0, "contestee", 2, "elevee", cfg) == cfg.c_min  # plancher
    # monotone en h : plus d'alerte, moins de confiance
    hs = [cs.confiance(1.0, "unanime", 0, a, cfg) for a in ("aucune", "moderee", "elevee")]
    assert hs[0] > hs[1] > hs[2]


def test_mediane_et_accord():
    assert cs.mediane_vers_zero([0, 1]) == 0
    assert cs.mediane_vers_zero([-1, 0]) == 0
    assert cs.mediane_vers_zero([-2, 1, 1]) == 1
    assert cs.accord([1, 1], 1) == 1.0
    assert cs.accord([-2, 2], 0) == pytest.approx(0.5)
    assert cs.borner(5, -2, 2, 1) == 1 and cs.borner(-5, -2, 2, 1) == -1


def test_langgraph_et_boucle_python_donnent_le_meme_debat(tmp_path):
    """L'ordonnanceur est interchangeable (D-009) : mêmes tours, mêmes niveaux, mêmes confiances."""

    def script(role, tour, actif):
        return 0 if role == MACRO else (1 if tour == 0 else 0 if tour == 1 else 1)

    sorties = {}
    for nom in ("langgraph", "boucle"):
        _, res = lancer(tmp_path / nom, script, overrides={"debate": {"orchestrateur": nom}})
        sorties[nom] = res
    a, b = sorties["langgraph"], sorties["boucle"]
    assert a.trace_graphe == b.trace_graphe
    assert [o.model_dump() for o in a.log.resultats] == [o.model_dump() for o in b.log.resultats]
    assert [t.niveaux for t in a.log.tours] == [t.niveaux for t in b.log.tours]


def test_un_seul_appel_d_arbitrage_pour_toutes_les_vues_contestees(tmp_path):
    ctx, res = lancer(tmp_path, lambda role, tour, actif: -2 if role == MACRO else 2)
    assert {o.statut for o in res.log.resultats} == {"contestee"} and len(res.log.resultats) == 3
    assert [a.nature for a in res.log.appels].count("arbitrage") == 1  # budget K_a <= 2 (L1 11.2)


def test_arbitrage_hors_bornes_remplace_par_la_mediane_et_signale(tmp_path):
    def handler(model, messages):
        if "Coordinateur : arbitrage" in messages[0]["content"]:
            return json.dumps({"arbitrages": []})  # réponse incomplète : rejetée
        return scripte(lambda role, tour, actif: -2 if role == MACRO else 2)(model, messages)

    ctx, res = lancer(tmp_path, None, handler=handler)
    assert all(o.niveau_final == 0 and "repli" in (o.arbitrage or "") for o in res.log.resultats)
    assert len(res.arbitrage_repli) == 3


def test_les_outils_ne_sont_pas_recalcules_aux_tours_de_revision(tmp_path):
    ctx, res = lancer(tmp_path, lambda role, tour, actif: -1 if role == MACRO else 1)
    for t in res.log.tours[1:]:
        for at in t.tours_agents:
            assert at.appels_outils and all(a.duree_ms == 0 for a in at.appels_outils)  # réutilisés
    tour0 = {at.agent: at.appels_outils for at in res.log.tours[0].tours_agents}
    tour1 = {at.agent: at.appels_outils for at in res.log.tours[1].tours_agents}
    for agent in tour0:
        ids0 = {a.resultat["meta"]["source_id"] for a in tour0[agent]}
        ids1 = {a.resultat["meta"]["source_id"] for a in tour1[agent]}
        assert ids1 <= ids0  # mêmes sorties d'outils (sous-ensemble des actifs encore ouverts)


def test_panne_du_fournisseur_pendant_une_revision_conserve_le_vote_precedent(tmp_path):
    from amundi_agentic.llm.types import ProviderError

    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)

    def handler(model, messages):
        if "Tour de débat" in messages[0]["content"] and "Agent Macro" in messages[0]["content"]:
            raise ProviderError("timeout", "délai dépassé")
        return base(model, messages)

    ctx, res = lancer(tmp_path, None, handler=handler, overrides={"debate": {"r_max": 1}})
    assert any("panne du fournisseur" in r.motif and r.agent == "macro" for r in res.log.rejets)
    assert {o.statut for o in res.log.resultats} == {"contestee"}  # les votes du tour 0 restent
    macro_tour1 = next(a for a in res.log.tours[1].tours_agents if a.agent == "macro")
    assert macro_tour1.vues == []  # aucun vote inventé pour la révision manquée
    assert res.log.tours[1].niveaux["or"]["macro"] == -1  # dernier vote valide conservé
