"""Schémas Pydantic partagés (L1 section 5, D-010) : EX-O1-03, EX-O1-09, EX-NF-10."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from amundi_agentic.schemas import (
    AgentTurn,
    DebateConfig,
    DebateLog,
    DebateOutcome,
    DebateRound,
    Decision5,
    ExecutionRecord,
    RunRecord,
    Source,
    View,
    coupure,
)

T = date(2024, 2, 1)
AVANT = datetime(2024, 1, 31, 12, 0, tzinfo=UTC)


def source(**kw):
    base = {
        "source_id": "s1",
        "type": "news",
        "titre": "Titre",
        "reference": "https://exemple.invalid/a",
        "date_publication": AVANT,
        "extrait": "extrait",
    }
    return Source(**{**base, **kw})


def vue(**kw):
    base = {
        "view_id": "v1",
        "actif": "actions_monde",
        "niveau_decision": "allocation",
        "date_analyse": T,
        "direction": "POSITIF",
        "confiance": 0.5,
        "arguments_pour": ["a"],
        "arguments_contre": ["b"],
        "sources": [source()],
        "profil_risque": "equilibre",
        "auteur": "macro",
        "statut": "individuelle",
        "run_id": "r1",
    }
    return View(**{**base, **kw})


def test_decision_cinq_niveaux_valeurs_admises():
    assert [d.n for d in Decision5] == [-2, -1, 0, 1, 2]
    assert Decision5.from_n(-2) is Decision5.FORTEMENT_NEGATIF
    with pytest.raises(ValueError):
        Decision5.from_n(3)
    with pytest.raises(ValidationError):
        vue(direction="TRES_POSITIF")


def test_vue_valide_et_horizon_par_defaut():
    v = vue()
    assert v.horizon_mois == 3
    assert v.rendement_excedentaire_attendu is None


def test_vue_sans_source_rejetee():
    with pytest.raises(ValidationError):
        vue(sources=[])


def test_vue_sans_argument_contre_rejetee():
    with pytest.raises(ValidationError):
        vue(arguments_contre=[])
    with pytest.raises(ValidationError):
        vue(arguments_pour=[])


def test_source_posterieure_a_t_rejetee():
    # La coupure est t 00:00 Europe/Paris : 2024-02-01 00:00 Paris = 2024-01-31 23:00 UTC.
    assert coupure(T) == datetime(2024, 1, 31, 23, 0, tzinfo=UTC)
    apres = datetime(2024, 1, 31, 23, 0, tzinfo=UTC)  # exactement la coupure : rejetée
    with pytest.raises(ValidationError, match="coupure"):
        vue(sources=[source(date_publication=apres)])
    with pytest.raises(ValidationError, match="coupure"):
        vue(sources=[source(), source(source_id="s2", date_publication=apres + timedelta(days=3))])
    vue(sources=[source(date_publication=apres - timedelta(seconds=1))])


def test_coupure_gere_l_heure_d_ete():
    assert coupure(date(2024, 7, 1)) == datetime(2024, 6, 30, 22, 0, tzinfo=UTC)


def test_date_de_publication_sans_fuseau_rejetee_et_ramenee_en_utc():
    with pytest.raises(ValidationError):
        source(date_publication=datetime(2024, 1, 1, 12, 0))
    s = source(date_publication=datetime(2024, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=2))))
    assert s.date_publication.utcoffset() == timedelta(0)
    assert s.date_publication.hour == 10


def test_sortie_outil_datee_par_sa_derniere_donnee():
    ok = source(type="sortie_outil", date_publication=datetime(2024, 1, 30, 21, 0, tzinfo=UTC))
    assert vue(sources=[ok]).sources[0].type == "sortie_outil"
    futur = source(type="sortie_outil", date_publication=datetime(2024, 2, 1, 21, 0, tzinfo=UTC))
    with pytest.raises(ValidationError, match="coupure"):
        vue(sources=[futur])


def test_extrait_limite_a_500_caracteres():
    with pytest.raises(ValidationError):
        source(extrait="x" * 501)
    source(extrait="x" * 500)


@pytest.mark.parametrize("c", [-0.01, 1.01, float("nan")])
def test_confiance_dans_zero_un(c):
    with pytest.raises(ValidationError):
        vue(confiance=c)


@pytest.mark.parametrize("c", [0, 0.5, 1])
def test_confiance_bornes_admises(c):
    assert vue(confiance=c).confiance == c


def test_horizon_entre_1_et_12_mois():
    for h in (0, 13):
        with pytest.raises(ValidationError):
            vue(horizon_mois=h)


def test_vue_contestee_bornee_a_un():
    vue(statut="contestee", direction="NEGATIF")
    with pytest.raises(ValidationError, match="±1"):
        vue(statut="contestee", direction="FORTEMENT_POSITIF")
    vue(statut="unanime", direction="FORTEMENT_POSITIF")


def test_actif_monetaire_sans_vue():
    with pytest.raises(ValidationError, match="résiduel"):
        vue(actif="monetaire_euro")


def test_rendement_en_decimal_pas_en_pourcentage():
    assert vue(rendement_excedentaire_attendu=0.02).rendement_excedentaire_attendu == 0.02
    with pytest.raises(ValidationError):
        vue(rendement_excedentaire_attendu=2)  # 2 % écrit « 2 » : refusé


def test_champ_inconnu_refuse():
    with pytest.raises(ValidationError):
        vue(champ_en_trop=1)


def test_date_analyse_n_accepte_pas_un_instant():
    with pytest.raises(ValidationError):
        vue(date_analyse=datetime(2024, 2, 1, 10, 0))


def test_avocat_du_diable_doit_produire_une_objection():
    with pytest.raises(ValidationError):
        AgentTurn(agent="macro", tour=1, role="avocat_du_diable")
    t = AgentTurn(agent="macro", tour=1, role="avocat_du_diable", objection="source X")
    assert t.vues == []


def test_tour_zero_est_la_collaboration():
    DebateRound(numero=0, phase="collaboration", tours_agents=[], niveaux={}, statut_apres_tour={})
    with pytest.raises(ValidationError):
        DebateRound(
            numero=1, phase="collaboration", tours_agents=[], niveaux={}, statut_apres_tour={}
        )
    with pytest.raises(ValidationError):
        DebateRound(numero=0, phase="debat", tours_agents=[], niveaux={}, statut_apres_tour={})
    with pytest.raises(ValidationError):
        DebateRound(
            numero=1,
            phase="debat",
            tours_agents=[],
            niveaux={"a": {"macro": 3}},
            statut_apres_tour={},
        )


def outcome(**kw):
    base = {
        "actif": "a",
        "niveau_final": 1,
        "statut": "consensus",
        "accord_A": 0.9,
        "tours_utilises": 2,
        "alerte_risque": "aucune",
        "confiance_finale": 0.4,
    }
    return DebateOutcome(**{**base, **kw})


def test_resultat_de_debat_contestee_borne():
    outcome()
    with pytest.raises(ValidationError):
        outcome(statut="contestee", niveau_final=2)
    with pytest.raises(ValidationError):
        outcome(confiance_finale=1.2)


def test_journal_de_debat_un_resultat_par_actif():
    cfg = DebateConfig(r_max=2, parametres_confiance={"c_max": 0.8}, graine_rotation=0)
    base = {
        "debate_id": "d1",
        "run_id": "r1",
        "date_analyse": T,
        "niveau_decision": "allocation",
        "actifs": ["a"],
        "profil_risque": "equilibre",
        "config": cfg,
        "tours": [],
        "rapport_coordinateur": "",
        "duree_s": 1.0,
        "tokens_entree": 0,
        "tokens_sortie": 0,
        "cout_eur": 0.0,
    }
    DebateLog(**base, resultats=[outcome()])
    with pytest.raises(ValidationError):
        DebateLog(**base, resultats=[])


def execution(**kw):
    base = {
        "appel_id": "a1",
        "run_id": "r1",
        "horodatage": AVANT,
        "agent": "macro",
        "tier": "main",
        "mode": "interactif",
        "modele_demande": "x/y",
        "modele_servi": "y",
        "fournisseur": "x",
        "prompt_id": "macro",
        "prompt_version": "1",
        "prompt_sha256": "a" * 64,
        "cle_cache": "b" * 64,
        "cache_hit": False,
        "graine": 0,
        "temperature": 0.0,
        "tokens_entree": 1,
        "tokens_sortie": 1,
        "cout_eur": 0.0,
        "latence_ms": 5,
        "date_donnees": T,
    }
    return ExecutionRecord(**{**base, **kw})


def test_execution_enregistre_modele_servi_prompt_et_graine():
    e = execution()
    assert (e.modele_servi, e.prompt_sha256, e.graine, e.mode) == ("y", "a" * 64, 0, "interactif")
    with pytest.raises(ValidationError):
        execution(prompt_sha256="pas-un-hash")
    with pytest.raises(ValidationError):
        execution(tokens_entree=-1)
    with pytest.raises(ValidationError):
        execution(cout_eur=-0.1)


def test_aucun_relais_en_mode_evaluation():
    with pytest.raises(ValidationError, match="relais"):
        execution(mode="evaluation", relais_utilise=True)
    execution(mode="evaluation", relais_utilise=False)


def run(**kw):
    base = {
        "run_id": "r1",
        "debut": AVANT,
        "commande": "x",
        "git_commit": "abc",
        "uv_lock_sha256": "0" * 64,
        "config_sha256": "1" * 64,
        "llm_config_sha256": "3" * 64,
        "profile": "prod",
        "modeles_demandes": {"main": "fournisseur/modele-fige"},
        "graine": 0,
        "mode": "interactif",
        "avertissement": "prototype académique",
    }
    return RunRecord(**{**base, **kw})


def test_preenregistrement_obligatoire_en_evaluation():
    run()
    with pytest.raises(ValidationError, match="pré-enregistrement"):
        run(mode="evaluation")
    run(mode="evaluation", preregistration_sha256="2" * 64, modele_servi_fige={"main": "m"})
    with pytest.raises(ValidationError):
        run(fin=AVANT - timedelta(seconds=1))
