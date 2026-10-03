"""Mode évaluation (D-024, EX-NF-13) : un modèle figé, aucun relais, pause sur 429 et 503,
arrêt si le modèle servi change."""

import json
from datetime import date

import pytest

from amundi_agentic.llm import ExecutionPausee, ModeleServiChange, load_config

T = date(2024, 2, 1)
MSG = [{"role": "user", "content": "Bonjour"}]


def jour(n):
    return date(2024, 2, n)


def test_config_evaluation_sans_relais_et_versions_figees(cfg):
    assert cfg.evaluation.fallback_enabled is False
    for nom in cfg.evaluation.models.values():
        assert "latest" not in nom
    with pytest.raises(ValueError, match="aucun relais"):
        load_config(
            overrides={"evaluation": {"fallback_enabled": True, "models": cfg.evaluation.models}}
        )


def test_evaluation_utilise_le_modele_fige_de_la_section_evaluation(fabrique, cfg):
    c = fabrique(mode="evaluation")
    r = c.complete(MSG, date_donnees=T, tier="main")
    assert c.mock.chat_calls[0]["model"] == cfg.evaluation.models["main"]
    assert r.record.mode == "evaluation" and r.record.relais_utilise is False
    r2 = c.complete(MSG, date_donnees=T, tier="light")
    assert c.mock.chat_calls[1]["model"] == cfg.evaluation.models["light"]
    assert r2.record.tier == "light"


def test_chaine_d_evaluation_a_un_seul_modele(cfg):
    for niveau in cfg.evaluation.models:
        assert len(cfg.chain(niveau, mode="evaluation", profile="prod")) == 1


def test_mode_evaluation_sans_relais_pause_sur_429(fabrique, cfg):
    c = fabrique(mode="evaluation")
    c.mock.fail("quota", cfg.retry.pause_429_max_waits + 1)
    with pytest.raises(ExecutionPausee) as e:
        c.complete(MSG, date_donnees=T)
    assert e.value.kind == "quota"
    assert c.sleeps == [cfg.retry.pause_429_wait_s] * cfg.retry.pause_429_max_waits
    # Jamais d'appel au modèle de relais ni à un autre modèle.
    assert {a["model"] for a in c.mock.chat_calls} == {cfg.evaluation.models["main"]}


def test_429_bref_en_evaluation_pause_puis_reprise_sans_arret(fabrique, cfg):
    c = fabrique(mode="evaluation")
    c.mock.fail("quota", 1)
    r = c.complete(MSG, date_donnees=T)
    assert r.text and c.sleeps == [cfg.retry.pause_429_wait_s]
    assert r.record.relais_utilise is False


def test_mode_evaluation_erreur_503_reessayee_puis_pause(fabrique, cfg):
    c = fabrique(mode="evaluation")
    c.mock.fail("unavailable", cfg.retry.max_attempts)
    with pytest.raises(ExecutionPausee) as e:
        c.complete(MSG, date_donnees=T)
    assert e.value.kind == "unavailable"
    assert len(c.mock.chat_calls) == cfg.retry.max_attempts
    assert len(c.sleeps) == cfg.retry.max_attempts - 1
    assert {a["model"] for a in c.mock.chat_calls} == {cfg.evaluation.models["main"]}


def test_503_intermittent_en_evaluation_reessaye_sans_changer_de_modele(fabrique, cfg):
    c = fabrique(mode="evaluation")
    c.mock.fail("unavailable", 2)
    r = c.complete(MSG, date_donnees=T)
    assert r.record.relais_utilise is False
    assert {a["model"] for a in c.mock.chat_calls} == {cfg.evaluation.models["main"]}


def test_modele_servi_constant_sur_un_run(fabrique, cfg):
    c = fabrique(mode="evaluation")
    modele = cfg.evaluation.models["main"]
    c.mock.set_served(modele, "version-A")
    c.complete(MSG, date_donnees=jour(1))
    c.complete(MSG, date_donnees=jour(2))
    assert c.modeles_servis_figes == {"main": "version-A"}
    c.mock.set_served(modele, "version-B")
    with pytest.raises(ModeleServiChange, match="version-A.*version-B"):
        c.complete(MSG, date_donnees=jour(3))


def test_arret_si_le_modele_servi_change_meme_depuis_le_cache(fabrique, cfg, tmp_path):
    modele = cfg.evaluation.models["main"]
    c1 = fabrique(mode="evaluation", run_dir=tmp_path / "run1")
    c1.mock.set_served(modele, "version-A")
    c1.complete(MSG, date_donnees=T)
    # Autre run, même cache : un modèle figé différent est refusé dès la lecture du cache.
    c2 = fabrique(mode="evaluation", run_dir=tmp_path / "run2")
    c2.mock.set_served(modele, "version-B")
    c2.complete(MSG, date_donnees=jour(2))  # gèle version-B dans ce run
    with pytest.raises(ModeleServiChange):
        c2.complete(MSG, date_donnees=T)  # entrée du cache servie par version-A


def test_modele_fige_persiste_dans_le_run_et_survit_au_redemarrage(fabrique, cfg, tmp_path):
    modele = cfg.evaluation.models["main"]
    run_dir = tmp_path / "run"
    c1 = fabrique(mode="evaluation", run_dir=run_dir)
    c1.mock.set_served(modele, "version-A")
    c1.complete(MSG, date_donnees=jour(1))
    assert json.loads((run_dir / "modele_servi_fige.json").read_text()) == {"main": "version-A"}
    c2 = fabrique(mode="evaluation", run_dir=run_dir)  # reprise du même run
    c2.mock.set_served(modele, "version-B")
    with pytest.raises(ModeleServiChange):
        c2.complete(MSG, date_donnees=jour(2))


def test_reponse_sans_modele_servi_refusee_en_evaluation(fabrique):
    from amundi_agentic.llm.types import RawCompletion

    c = fabrique(mode="evaluation")
    c.mock.push(RawCompletion("texte", ""))
    with pytest.raises(ModeleServiChange, match="invérifiable"):
        c.complete(MSG, date_donnees=T)


def test_mode_interactif_tolere_un_changement_de_modele_servi(fabrique, cfg):
    c = fabrique(mode="interactif")
    c.mock.set_served(cfg.models["main"], "v1")
    c.complete(MSG, date_donnees=jour(1))
    c.mock.set_served(cfg.models["main"], "v2")
    assert c.complete(MSG, date_donnees=jour(2)).record.modele_servi == "v2"


def test_fin_d_entrainement_relevee_par_modele_servi(fabrique, cfg):
    config = load_config(overrides={"training_cutoff": {"version-A": "2025-01-31"}})
    c = fabrique(config=config, mode="evaluation")
    c.mock.set_served(config.evaluation.models["main"], "version-A")
    r = c.complete(MSG, date_donnees=T)
    assert r.record.fin_entrainement_modele == date(2025, 1, 31)
    assert fabrique().complete(MSG, date_donnees=T).record.fin_entrainement_modele is None
