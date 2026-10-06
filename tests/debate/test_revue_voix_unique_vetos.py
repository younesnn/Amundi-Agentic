"""Revue indépendante, 2e passe : statut `voix_unique`, allocation entièrement vetoed, agent ESG
(point-in-time), commande (code 2 sans trace)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from agents_helpers import T, fabrique_ctx
from debate_helpers import scripte
from pydantic import ValidationError

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.providers import SyntheticData
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.data.models import EsgRecord
from amundi_agentic.debate import consensus as cs
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.debate.run import executer
from amundi_agentic.schemas import DebateOutcome, View

CLASSES = ["actions_etats_unis", "souverain_euro", "or"]
MACRO = "Agent Macro"
S = load_settings()
CONF = S.confidence


def lancer(tmp_path, handler, *, overrides=None, assets=CLASSES, live=True):
    ctx = fabrique_ctx(tmp_path, handler=handler, settings_overrides=overrides)
    votants = construire_votants(ctx, "allocation", live=live)
    esg = EsgAgent().evaluer(ctx, "allocation", assets)
    res = run_debate(ctx, "allocation", assets, votants, Coordinator(), esg, risk_agent=RiskAgent())
    return ctx, res


def sauf(noms, base, *, tours=None, actifs=None):
    """Handler : les agents de `noms` répondent n'importe quoi (rejetés) ; `tours` limite aux tours
    listés ; `actifs` : seul l'actif cité est empoisonné (chiffre inventé)."""

    def handler(model, messages):
        systeme = messages[0]["content"]
        cible = any(n in systeme for n in noms) and "Coordinateur" not in systeme
        import re

        m = re.search(r"Tu es au tour (\d+) du débat", systeme)
        tour = int(m.group(1)) if m else 0
        if cible and (tours is None or tour in tours):
            if actifs is None:
                return "pas du json"
            out = json.loads(base(model, messages))
            for v in out.get("vues", []):
                if v["actif"] in actifs:
                    v["arguments_pour"] = ["rendement de 87,65 %"]
            return json.dumps(out)
        return base(model, messages)

    return handler


# --------------------------------------------------------------------------- voix_unique
def test_deux_agents_sur_trois_rejetes_au_tour_zero_donnent_voix_unique_sans_debat(tmp_path):
    base = scripte(lambda role, tour, actif: 2)
    ctx, res = lancer(tmp_path, sauf(["Agent Valuation", "Agent Sentiment"], base))
    assert res.log.votants == ["macro"]
    assert [t.numero for t in res.log.tours] == [0]  # figé dès le tour 0 : aucun tour de débat
    assert not any(a.nature == "revision" for a in res.log.appels)  # l'avocat n'est jamais appelé
    for o in res.log.resultats:
        assert o.statut == "voix_unique" and o.niveau_final == 1  # +2 voté, borné à +1
        assert o.confiance_finale <= CONF.plafond_voix_unique == 0.32
        assert o.tours_utilises == 0
    assert res.log.tours[0].statut_apres_tour == dict.fromkeys(CLASSES, "voix_unique")


def test_un_seul_agent_rejete_sur_trois_reste_un_vrai_debat_a_deux(tmp_path):
    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)
    ctx, res = lancer(tmp_path, sauf(["Agent Sentiment"], base))
    assert sorted(res.log.votants) == ["macro", "valuation"]
    assert {o.statut for o in res.log.resultats} == {"contestee"}  # K=2 valides : pas voix_unique


def test_le_statut_depend_du_moment_ou_l_agent_est_ecarte(tmp_path):
    base = scripte(lambda role, tour, actif: -1 if role == MACRO else 1)
    # écarté APRÈS le tour 0 (échec aux tours de révision) : son vote du tour 0 est conservé
    _, tard = lancer(tmp_path / "tard", sauf(["Agent Valuation"], base, tours={1, 2}), live=False)
    assert {o.statut for o in tard.log.resultats} == {"contestee"}
    assert all(len(v) == 2 for r in tard.log.tours for v in r.niveaux.values())
    # écarté AU tour 0 : une seule voix, `voix_unique`
    _, tot = lancer(tmp_path / "tot", sauf(["Agent Valuation"], base, tours={0}), live=False)
    assert {o.statut for o in tot.log.resultats} == {"voix_unique"}


def test_voix_unique_pour_un_actif_et_debat_normal_pour_les_autres(tmp_path):
    base = scripte(lambda role, tour, actif: -2 if role == MACRO else 2)
    ctx, res = lancer(
        tmp_path, sauf(["Agent Valuation"], base, tours={0}, actifs={"souverain_euro"}), live=False
    )
    par = {o.actif: o for o in res.log.resultats}
    assert par["souverain_euro"].statut == "voix_unique"
    assert (
        par["souverain_euro"].confiance_finale <= 0.32
        and abs(par["souverain_euro"].niveau_final) <= 1
    )
    assert par["or"].statut == par["actions_etats_unis"].statut == "contestee"
    assert [a.nature for a in res.log.appels].count(
        "arbitrage"
    ) == 1  # un seul appel, pour les 2 contestés
    assert "souverain_euro" not in json.dumps(
        [a.messages for a in res.log.appels if a.nature == "arbitrage"]
    )  # la voix unique n'est jamais arbitrée
    assert {o.actif for o in res.log.resultats if o.statut == "contestee"} == {
        "or",
        "actions_etats_unis",
    }


def test_voix_unique_non_transmise_par_defaut_et_seulement_sur_demande(tmp_path):
    base = scripte(lambda role, tour, actif: 1)
    ctx, res = lancer(tmp_path, sauf(["Agent Valuation"], base, tours={0}), live=False)
    assert ctx.settings.debate.transmettre_voix_unique is False
    assert res.vues_finales and {v.statut for v in res.vues_finales} == {"voix_unique"}
    assert res.vues_transmises(True) == [] == res.vues_transmises(False)
    assert len(res.vues_transmises(True, voix_unique_transmise=True)) == len(res.vues_finales)
    assert (
        res.vues_transmises(True, voix_unique_transmise=ctx.settings.debate.transmettre_voix_unique)
        == []
    )


def test_voix_unique_journalisee_et_mentionnee_dans_le_rapport(tmp_path):
    base = scripte(lambda role, tour, actif: 1)
    ctx = fabrique_ctx(tmp_path, handler=sauf(["Agent Valuation"], base, tours={0}))
    sortie = executer(ctx, classes=CLASSES, titres=[], live=False)
    assert "voix unique" in sortie.rapport_md.lower()
    log = sortie.debats[0].log
    assert {o.statut for o in log.resultats} == {"voix_unique"} and log.rejets
    assert all(r.agent == "valuation" for r in log.rejets if r.tour == 0)


def test_schema_coherent_voix_unique_borne_a_un():
    from agents_helpers import fabrique_ctx as _f  # noqa: F401

    base = dict(
        view_id="v", actif="or", niveau_decision="allocation", date_analyse=T, confiance=0.3,
        arguments_pour=["a"], arguments_contre=["b"], profil_risque="equilibre", auteur="x",
        run_id="r", statut="voix_unique",
    )  # fmt: skip
    from amundi_agentic.schemas import Source

    src = Source(
        source_id="s", type="news", titre="t", reference="r",
        date_publication=datetime(2024, 1, 1, tzinfo=UTC), extrait="e",
    )  # fmt: skip
    View(**base, direction="POSITIF", sources=[src])
    with pytest.raises(ValidationError):
        View(**base, direction="FORTEMENT_POSITIF", sources=[src])
    kw = dict(actif="or", statut="voix_unique", accord_A=1.0, tours_utilises=0,
              alerte_risque="aucune", confiance_finale=0.3)  # fmt: skip
    DebateOutcome(niveau_final=1, **kw)
    with pytest.raises(ValidationError):
        DebateOutcome(niveau_final=2, **kw)


@pytest.mark.parametrize(
    "alerte,tours", [("aucune", 0), ("moderee", 0), ("elevee", 0), ("aucune", 3)]
)
def test_confiance_voix_unique_formule_et_plafond(alerte, tours):
    brut = CONF.c_max * 1.0 * 1.0 * max(0.0, 1 - CONF.rho_par_tour * tours) * CONF.h[alerte]
    attendu = min(0.32, max(CONF.c_min, min(CONF.c_max, brut)))
    assert cs.confiance(1.0, "voix_unique", tours, alerte, CONF) == pytest.approx(attendu)
    assert cs.confiance(1.0, "voix_unique", tours, alerte, CONF) <= 0.32
    assert cs.confiance(1.0, "voix_unique", tours, alerte, CONF) >= CONF.c_min


def test_le_seuil_min_votants_valides_est_une_vraie_regle(tmp_path):
    base = scripte(lambda role, tour, actif: 1)
    # seuil à 1 : un agent seul redevient `unanime` ; seuil à 3 : deux agents ne suffisent plus
    _, un = lancer(tmp_path / "1", sauf(["Agent Valuation"], base, tours={0}), live=False,
                   overrides={"consensus": {"min_votants_valides": 1}})  # fmt: skip
    assert {o.statut for o in un.log.resultats} == {"unanime"}
    _, trois = lancer(tmp_path / "3", scripte(lambda r, t, a: 1),
                      overrides={"consensus": {"min_votants_valides": 3}}, live=False)  # fmt: skip
    assert {o.statut for o in trois.log.resultats} == {"voix_unique"}


# --------------------------------------------------------------------------- allocation entièrement vetoed
def test_allocation_entierement_vetoed_ecartee_sans_exception_ni_appel_d_analyse(tmp_path):
    ctx = fabrique_ctx(
        tmp_path,
        settings_overrides={
            "esg": {"etf_criteres_requis": ["tobacco"], "llm_explique_les_vetos": False}
        },
        handler=scripte(lambda r, t, a: 1),
    )
    sortie = executer(ctx, classes=CLASSES, titres=["AAA", "BBB"], live=False)
    assert sortie.debats and all(d.log.niveau_decision == "titre" for d in sortie.debats)
    assert sorted(sortie.exclus_esg) == sorted(CLASSES)
    assert "allocation" in sortie.ecartes and "veto" in sortie.ecartes["allocation"]
    assert not any("allocation" in d.log.debate_id for d in sortie.debats)
    assert all(v.actif not in CLASSES for v in sortie.vues_finales)
    assert "Débats écartés" in sortie.rapport_md and "allocation" in sortie.rapport_md
    for a in ctx.llm.mock.chat_calls:  # aucun appel d'analyse d'allocation
        assert "Agent Macro" not in a["messages"][0]["content"]


def test_allocation_partiellement_vetoed_ne_debat_que_des_actifs_autorises(tmp_path):
    ctx = fabrique_ctx(
        tmp_path,
        settings_overrides={
            "esg": {"etf_criteres_requis": ["tobacco"], "llm_explique_les_vetos": False}
        },
        handler=scripte(lambda r, t, a: 1),
    )
    ticker_or = ctx.data.classes["or"]

    class Vue:
        def proven_exclusions(self, ticker):
            return frozenset({"tobacco"}) if ticker == ticker_or else frozenset()

        def sfdr(self, ticker):
            return "article 8"

    ctx.data.etf_esg = lambda: Vue()
    sortie = executer(ctx, classes=CLASSES, titres=[], live=False)
    assert sortie.ecartes == {}  # pas écarté : un actif reste autorisé
    assert [d.log.actifs for d in sortie.debats] == [["or"]]
    assert sorted(sortie.exclus_esg) == ["actions_etats_unis", "souverain_euro"]


def test_aucun_appel_llm_du_tout_si_tout_est_vetoed_et_sans_explication(tmp_path):
    ctx = fabrique_ctx(
        tmp_path,
        settings_overrides={
            "esg": {"etf_criteres_requis": ["tobacco"], "llm_explique_les_vetos": False}
        },
    )
    sortie = executer(ctx, classes=CLASSES, titres=[], live=False)
    assert ctx.llm.mock.chat_calls == [] and sortie.debats == [] and sortie.vues_finales == []
    assert sortie.rapport_md and "pas un conseil" in sortie.rapport_md


# --------------------------------------------------------------------------- agent ESG point-in-time
def _donnees_esg(observe, **kw):
    class D(SyntheticData):
        def esg(self, asset_id):
            return EsgRecord(
                asset_id=asset_id, score=None, score_source=None, exclusions=("tobacco",),
                exclusion_basis="sic", observed_at=observe, non_point_in_time=kw.get("npit", False),
                notes=(),
            )  # fmt: skip

    return D(T)


@pytest.mark.parametrize("delta", [timedelta(days=30), timedelta(hours=12), timedelta(seconds=1)])
def test_enregistrement_esg_posterieur_a_la_coupure_est_ignore_et_signale(tmp_path, delta):
    from amundi_agentic.schemas import coupure

    ctx = fabrique_ctx(tmp_path)
    ctx.data = _donnees_esg(coupure(T) + delta)
    e = EsgAgent().evaluer(ctx, "titre", ["AAA"])["AAA"]
    assert e.veto is False and not e.motifs
    assert any("ignoré (point-in-time)" in x for x in e.limites)


def test_enregistrement_esg_une_seconde_avant_la_coupure_est_utilise(tmp_path):
    from amundi_agentic.schemas import coupure

    ctx = fabrique_ctx(tmp_path)
    ctx.data = _donnees_esg(coupure(T) - timedelta(seconds=1))
    e = EsgAgent().evaluer(ctx, "titre", ["AAA"])["AAA"]
    assert e.veto is True and e.point_in_time is True


def test_enregistrement_non_point_in_time_explicite_est_signale_et_non_point_in_time(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ctx.data = _donnees_esg(datetime(2030, 1, 1, tzinfo=UTC), npit=True)  # collecté après t, marqué
    e = EsgAgent().evaluer(ctx, "titre", ["AAA"])["AAA"]
    assert e.point_in_time is False and any("non point-in-time" in x for x in e.limites)


def test_le_llm_ne_voit_jamais_un_enregistrement_posterieur(tmp_path):
    from amundi_agentic.schemas import coupure

    ctx = fabrique_ctx(tmp_path, handler=politique_simulee)
    ctx.data = _donnees_esg(coupure(T) + timedelta(days=5))
    sortie = executer(ctx, classes=[], titres=["AAA"], live=False)
    assert sortie.exclus_esg == [] and sortie.debats  # pas de veto fondé sur le futur : débat tenu


def test_constat_un_enregistrement_non_point_in_time_futur_peut_fonder_un_veto(tmp_path):
    """Limite documentée (non bloquante) : marqué `non_point_in_time` par la couche data/, un
    enregistrement postérieur à t reste utilisé (mode live ou sensibilité). L'agent ESG ignore le
    mode d'exécution : en évaluation, c'est à la couche data/ de ne jamais servir de tels
    enregistrements ; l'agent signale seulement « donnée ESG non point-in-time »."""
    ctx = fabrique_ctx(tmp_path)
    ctx.data = _donnees_esg(datetime(2030, 1, 1, tzinfo=UTC), npit=True)
    e = EsgAgent().evaluer(ctx, "titre", ["AAA"])["AAA"]
    assert e.veto is True and e.point_in_time is False
