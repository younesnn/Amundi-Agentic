"""Revue indépendante : plafond de confiance FINALE imposé par une limite de données (repli du
découpage RAG, limites multiples, transversales), sous tous les statuts de débat."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from agents_helpers import T, fabrique_ctx
from debate_helpers import scripte

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.evidence import Limite
from amundi_agentic.agents.ports import FakePassage
from amundi_agentic.agents.providers import rag_synthetique
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.agents.valuation import ValuationAgent
from amundi_agentic.debate import consensus as cs
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.debate.run import executer

CONF = load_settings().confidence
PLAFOND = load_settings().fundamental.plafond_confiance_decoupage_echoue
FUND = "Agent Fundamental"


@dataclass
class ResultatRepli:
    passages: tuple
    section_fallback: bool = True
    fallback_accessions: list[str] = field(default_factory=lambda: ["0000050863-25-000013"])


class RagRepli:
    def __init__(self, en_repli=("AAA",)):
        self.base = rag_synthetique(T, ("AAA", "BBB", "CCC"))
        self.en_repli = set(en_repli)

    def index_filings(self, ticker, as_of):
        return self.base.index_filings(ticker, as_of)

    def query(self, ticker, question, as_of, *, k=5):
        res = self.base.query(ticker, question, as_of, k=k)
        if ticker not in self.en_repli:
            return res
        return ResultatRepli(
            tuple(FakePassage(p.text, "Document", p.score, p.source) for p in res.passages)
        )


class ValuationAvecLimites(ValuationAgent):
    """Valuation qui ajoute des limites de données (pour tester limites multiples et transversales)."""

    def __init__(self, level, limites):
        super().__init__(level)
        self._limites = limites

    def collecter(self, ctx, assets):
        ev = super().collecter(ctx, assets)
        ev.limites.extend(self._limites)
        return ev


def titre(
    tmp_path, script, *, ticker="AAA", repli=("AAA",), limites=(), handler=None, overrides=None
):
    ctx = fabrique_ctx(tmp_path, handler=handler or scripte(script), settings_overrides=overrides)
    ctx.rag = RagRepli(repli)
    votants = [
        ValuationAvecLimites("titre", list(limites)) if a.name == "valuation" else a
        for a in construire_votants(ctx, "titre", live=True)
    ]
    esg = EsgAgent().evaluer(ctx, "titre", [ticker])
    res = run_debate(ctx, "titre", [ticker], votants, Coordinator(), esg, risk_agent=RiskAgent())
    return ctx, res


def naturel(o):
    return cs.confiance(o.accord_A, o.statut, o.tours_utilises, o.alerte_risque, CONF)


def verifie_coherence(res):
    for o in res.log.resultats:
        v = next(x for x in res.vues_finales if x.actif == o.actif)
        assert v.confiance == o.confiance_finale  # View.confiance == DebateOutcome.confiance_finale
        assert o.confiance_finale <= naturel(o) + 1e-12  # un plafond ne relève jamais


# --------------------------------------------------------------------------- repli du découpage
def test_unanime_en_repli_plafonne_a_0_4():
    assert PLAFOND == 0.4


def test_unanimite_a_trois_agents_confiance_finale_plafonnee(tmp_path):
    ctx, res = titre(tmp_path, lambda r, t, a: 1)
    (o,) = res.log.resultats
    assert o.statut == "unanime" and naturel(o) > PLAFOND  # sans plafond : 0,8 x h
    assert o.confiance_finale == pytest.approx(PLAFOND)
    assert o.plafonnee_par and "Découpage par sections en repli" in o.plafonnee_par
    assert "(plafond 0.4)" in o.plafonnee_par
    verifie_coherence(res)
    assert res.vues_finales[0].confiance == pytest.approx(PLAFOND)


def test_consensus_ecart_un_plafonne_seulement_si_le_naturel_depasse_le_plafond(tmp_path):
    ctx, res = titre(tmp_path, lambda role, t, a: 0 if FUND in role else 1)
    (o,) = res.log.resultats
    assert o.statut == "consensus"
    assert o.confiance_finale == pytest.approx(min(naturel(o), PLAFOND))
    assert (o.plafonnee_par is not None) == (naturel(o) > PLAFOND + 1e-12)  # renseigné si utile
    verifie_coherence(res)


def test_plafonnee_par_renseigne_si_et_seulement_si_le_plafond_a_joue_dans_les_deux_cas(tmp_path):
    """Cas où le naturel dépasse (h = 1) et cas où il ne dépasse pas (h = 0,6 via alerte forcée)."""
    _, haut = titre(tmp_path / "a", lambda r, t, a: 1)
    assert haut.log.resultats[0].plafonnee_par is not None
    _, bas = titre(
        tmp_path / "b",
        lambda r, t, a: 1,
        overrides={
            "confidence": {
                "alerte_si_indisponible": "elevee",
                "h": {"aucune": 1.0, "moderee": 0.8, "elevee": 0.2},
            }
        },
    )
    o = bas.log.resultats[0]
    if naturel(o) <= PLAFOND:
        assert o.plafonnee_par is None and o.confiance_finale == pytest.approx(naturel(o))


def test_contestee_deja_sous_le_plafond_n_est_pas_relevee_ni_marquee(tmp_path):
    ctx, res = titre(tmp_path, lambda role, t, a: -2 if FUND in role else 2)
    (o,) = res.log.resultats
    assert o.statut == "contestee" and o.confiance_finale <= 0.32 < PLAFOND
    assert o.confiance_finale == pytest.approx(naturel(o)) and o.plafonnee_par is None
    verifie_coherence(res)


def test_voix_unique_deja_sous_le_plafond_non_relevee_et_plafond_plus_bas_applique(tmp_path):
    base = scripte(lambda r, t, a: 1)

    def handler(model, messages):
        s = messages[0]["content"]
        if ("Agent Valuation" in s or "Agent Sentiment" in s) and "Coordinateur" not in s:
            return "pas du json"
        return base(model, messages)

    _, res = titre(tmp_path / "a", None, handler=handler)
    (o,) = res.log.resultats
    assert o.statut == "voix_unique" and o.confiance_finale <= 0.32 and o.plafonnee_par is None
    # plafond de repli plus bas que celui de la voix unique : c'est le plus bas qui gagne
    _, bas = titre(
        tmp_path / "b", None, handler=handler,
        overrides={"fundamental": {"plafond_confiance_decoupage_echoue": 0.2}},
    )  # fmt: skip
    ob = bas.log.resultats[0]
    assert ob.statut == "voix_unique" and ob.confiance_finale == pytest.approx(0.2)
    assert ob.plafonnee_par and "(plafond 0.2)" in ob.plafonnee_par


def test_titre_non_en_repli_n_est_pas_plafonne_meme_avec_un_voisin_en_repli(tmp_path):
    ctx, res = titre(tmp_path, lambda r, t, a: 1, ticker="BBB", repli=("AAA",))
    (o,) = res.log.resultats
    assert o.confiance_finale == pytest.approx(naturel(o)) and o.plafonnee_par is None
    assert o.confiance_finale > PLAFOND


# --------------------------------------------------------------------------- limites multiples
def test_limites_multiples_le_plus_bas_plafond_gagne(tmp_path):
    lim = [Limite("AAA", "limite A", 0.3), Limite("AAA", "limite B", 0.25)]
    ctx, res = titre(tmp_path, lambda r, t, a: 1, limites=lim)
    (o,) = res.log.resultats
    assert o.confiance_finale == pytest.approx(0.25)
    assert "limite B" in o.plafonnee_par and "(plafond 0.25)" in o.plafonnee_par
    verifie_coherence(res)


def test_limite_d_un_autre_actif_est_sans_effet(tmp_path):
    ctx, res = titre(
        tmp_path, lambda r, t, a: 1, ticker="BBB", repli=(), limites=[Limite("AAA", "autre", 0.1)]
    )
    (o,) = res.log.resultats
    assert o.confiance_finale == pytest.approx(naturel(o)) and o.plafonnee_par is None


def test_limite_sans_plafond_ne_plafonne_rien(tmp_path):
    ctx, res = titre(
        tmp_path, lambda r, t, a: 1, ticker="BBB", repli=(), limites=[Limite("BBB", "info", None)]
    )
    (o,) = res.log.resultats
    assert o.confiance_finale == pytest.approx(naturel(o)) and o.plafonnee_par is None


def test_limite_transversale_plafonne_tous_les_actifs_de_l_allocation(tmp_path):
    ctx = fabrique_ctx(tmp_path, handler=scripte(lambda r, t, a: 1))
    votants = [
        ValuationAvecLimites("allocation", [Limite(None, "limite transversale", 0.25)])
        if a.name == "valuation"
        else a
        for a in construire_votants(ctx, "allocation", live=False)
    ]
    classes = ["actions_etats_unis", "souverain_euro", "or"]
    esg = EsgAgent().evaluer(ctx, "allocation", classes)
    res = run_debate(
        ctx, "allocation", classes, votants, Coordinator(), esg, risk_agent=RiskAgent()
    )
    assert len(res.log.resultats) == 3
    for o in res.log.resultats:
        assert (
            o.confiance_finale == pytest.approx(0.25) and "limite transversale" in o.plafonnee_par
        )
    verifie_coherence(res)


# --------------------------------------------------------------------------- journal et rapport
def test_plafonnee_par_dans_le_journal_et_le_rapport(tmp_path):
    ctx = fabrique_ctx(tmp_path, handler=scripte(lambda r, t, a: 1))
    ctx.rag = RagRepli()
    sortie = executer(ctx, classes=[], titres=["AAA", "BBB"], live=True)
    par = {o.actif: o for d in sortie.debats for o in d.log.resultats}
    assert par["AAA"].plafonnee_par and par["BBB"].plafonnee_par is None
    from amundi_agentic.schemas import DebateLog

    log = next(d.log for d in sortie.debats if d.log.actifs == ["AAA"])
    assert "plafonnee_par" in json.loads(log.model_dump_json())["resultats"][0]
    assert DebateLog.model_validate_json(log.model_dump_json()) == log
    assert (
        "confiance plafonnée par :" in sortie.rapport_md
        and "AAA" in sortie.rapport_md.split("confiance plafonnée par")[0].splitlines()[-1]
    )
    assert sortie.rapport_md.count("confiance plafonnée par :") == 1  # seulement AAA


@pytest.mark.parametrize("script", ["unanime", "consensus", "contestee"])
def test_les_deux_orchestrateurs_plafonnent_de_la_meme_facon(tmp_path, script):
    scripts = {
        "unanime": lambda r, t, a: 1,
        "consensus": lambda role, t, a: 0 if FUND in role else 1,
        "contestee": lambda role, t, a: -2 if FUND in role else 2,
    }
    empreintes = {}
    for orch in ("langgraph", "boucle"):
        _, res = titre(
            tmp_path / orch, scripts[script], overrides={"debate": {"orchestrateur": orch}}
        )
        o = res.log.resultats[0]
        empreintes[orch] = (o.statut, round(o.confiance_finale, 9), o.plafonnee_par, o.niveau_final)
        verifie_coherence(res)
    assert empreintes["langgraph"] == empreintes["boucle"]
