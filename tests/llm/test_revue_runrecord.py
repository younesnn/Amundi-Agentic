"""Revue indépendante : `RunRecord`, `LLMClient.run_fields()`, `tier_demande`."""

import hashlib
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from amundi_agentic.llm import load_config
from amundi_agentic.llm.config import CONFIG_PATH
from amundi_agentic.schemas import ExecutionRecord, RunRecord

T = date(2024, 2, 1)
MSG = [{"role": "user", "content": "Bonjour"}]
DEBUT = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


def run_record(client, **kw):
    base = dict(
        run_id="r1",
        debut=DEBUT,
        commande="amundi run",
        git_commit="abc",
        uv_lock_sha256="0" * 64,
        config_sha256="1" * 64,
        preregistration_sha256="2" * 64 if client.mode == "evaluation" else None,
        avertissement="prototype académique",
        **client.run_fields(),
    )
    return RunRecord(**{**base, **kw})


def run_eval(fabrique, cfg, tmp_path):
    c = fabrique(mode="evaluation", run_dir=tmp_path / "run")
    c.complete(MSG, date_donnees=T, tier="main")
    c.complete(MSG, date_donnees=T, tier="light")
    c.embed(["a"], date_donnees=T)
    c.complete(MSG, date_donnees=T, tier="main")  # cache hit
    return c


def test_run_fields_renvoie_tous_les_champs_que_le_client_connait(fabrique, cfg, tmp_path):
    c = run_eval(fabrique, cfg, tmp_path)
    champs = c.run_fields()
    assert set(champs) == {
        "profile",
        "mode",
        "graine",
        "modeles_demandes",
        "llm_config_sha256",
        "modele_servi_fige",
        "fin_entrainement",
        "usage",
    }
    assert champs["profile"] == "prod" and champs["mode"] == "evaluation"
    assert champs["graine"] == cfg.defaults.seed
    assert champs["modeles_demandes"] == {
        **cfg.evaluation.models,
        "embed": cfg.embeddings["prod"],
    }
    assert set(champs["modele_servi_fige"]) == {"main", "light", "embed"}
    assert set(champs["fin_entrainement"]) == {"main", "light", "embed"}
    assert champs["usage"] == {"appels": 3, "cache_hits": 1}
    assert champs["llm_config_sha256"] == hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()


def test_run_fields_construit_un_run_record_valide_en_evaluation(fabrique, cfg, tmp_path):
    c = run_eval(fabrique, cfg, tmp_path)
    r = run_record(c)
    assert r.modele_servi_fige == c.modeles_servis_figes and r.profile == "prod"
    assert r.mode == "evaluation" and r.modeles_demandes["main"] == cfg.evaluation.models["main"]
    assert RunRecord.model_validate_json(r.model_dump_json()) == r  # aller-retour JSON


def test_run_fields_fin_d_entrainement_releve_pour_les_niveaux_figes(fabrique, cfg, tmp_path):
    modele_servi = cfg.evaluation.models["main"].split("/", 1)[1]
    c2 = load_config(overrides={"training_cutoff": {modele_servi: date(2025, 1, 31)}})
    c = fabrique(config=c2, mode="evaluation")
    c.complete(MSG, date_donnees=T, tier="main")
    assert c.run_fields()["fin_entrainement"] == {"main": date(2025, 1, 31)}
    assert run_record(c).fin_entrainement == {"main": date(2025, 1, 31)}


def test_run_fields_interactif_sans_gel(fabrique, cfg):
    c = fabrique(mode="interactif")
    c.complete(MSG, date_donnees=T)
    champs = c.run_fields()
    assert champs["modele_servi_fige"] is None and champs["fin_entrainement"] == {}
    assert champs["mode"] == "interactif" and champs["profile"] == "prod"
    assert run_record(c).preregistration_sha256 is None


def test_run_fields_profil_dev_interactif(fabrique, cfg):
    c = fabrique(profile="dev")
    assert c.run_fields()["profile"] == "dev"
    assert run_record(c).profile == "dev"


def test_run_fields_usage_compte_les_appels_reels_et_les_hits(fabrique):
    c = fabrique()
    c.complete(MSG, date_donnees=T)
    c.complete(MSG, date_donnees=T)
    assert c.run_fields()["usage"] == {"appels": 1, "cache_hits": 1}


def test_llm_config_sha256_change_quand_la_config_effective_change(fabrique, cfg):
    a = fabrique().run_fields()["llm_config_sha256"]
    b = fabrique(config=load_config(overrides={"defaults": {"temperature": 0.5}})).run_fields()[
        "llm_config_sha256"
    ]
    c = fabrique(config=load_config(overrides={"defaults": {"temperature": 0.5}})).run_fields()[
        "llm_config_sha256"
    ]
    assert a != b and b == c  # déterministe, sensible à la surcharge


def test_champs_de_run_fields_sont_tous_des_champs_de_run_record(fabrique):
    assert set(fabrique().run_fields()) <= set(RunRecord.model_fields)


def test_tier_demande_est_un_champ_d_execution_record():
    assert "tier_demande" in ExecutionRecord.model_fields


@pytest.mark.parametrize("manquant", ["profile", "modeles_demandes", "llm_config_sha256"])
def test_champs_obligatoires_de_run_record(fabrique, manquant):
    c = fabrique()
    champs = {**c.run_fields()}
    champs.pop(manquant)
    with pytest.raises(ValidationError, match=manquant):
        RunRecord(
            run_id="r",
            debut=DEBUT,
            commande="x",
            git_commit="g",
            uv_lock_sha256="0" * 64,
            config_sha256="1" * 64,
            avertissement="a",
            **champs,
        )


def test_run_record_valide_les_nouveaux_champs(fabrique, cfg, tmp_path):
    c = run_eval(fabrique, cfg, tmp_path)
    run_record(c)  # référence valide
    with pytest.raises(ValidationError, match="profil prod"):
        run_record(c, profile="dev")
    with pytest.raises(ValidationError):
        run_record(c, llm_config_sha256="pas-un-hash")
    with pytest.raises(ValidationError):
        run_record(c, llm_config_sha256="A" * 64)  # hexadécimal minuscule exigé
    with pytest.raises(ValidationError):
        run_record(c, modele_servi_fige="une-chaine")  # un dict par niveau, plus une chaîne
    with pytest.raises(ValidationError):
        run_record(c, modele_servi_fige={"main": 3})
    with pytest.raises(ValidationError, match="niveaux figés"):
        run_record(c, fin_entrainement={"inconnu": date(2025, 1, 1)})
    with pytest.raises(ValidationError, match="pré-enregistrement"):
        run_record(c, preregistration_sha256=None)
    with pytest.raises(ValidationError, match="antérieure"):
        run_record(c, fin=datetime(2026, 10, 3, 8, 0, tzinfo=UTC))
    with pytest.raises(ValidationError):
        run_record(c, champ_inconnu=1)


def test_fin_entrainement_sans_gel_est_refuse():
    with pytest.raises(ValidationError, match="niveaux figés"):
        RunRecord(
            run_id="r",
            debut=DEBUT,
            commande="x",
            git_commit="g",
            uv_lock_sha256="0" * 64,
            config_sha256="1" * 64,
            llm_config_sha256="3" * 64,
            profile="prod",
            modeles_demandes={},
            fin_entrainement={"main": date(2025, 1, 1)},
            graine=0,
            mode="interactif",
            avertissement="a",
        )


def test_run_record_interactif_accepte_profil_dev():
    r = RunRecord(
        run_id="r",
        debut=DEBUT,
        commande="x",
        git_commit="g",
        uv_lock_sha256="0" * 64,
        config_sha256="1" * 64,
        llm_config_sha256="3" * 64,
        profile="dev",
        modeles_demandes={},
        graine=0,
        mode="interactif",
        avertissement="a",
    )
    assert r.modele_servi_fige is None and r.usage == {}


def test_config_construite_sans_load_config_donne_un_hash_sha256_deterministe_et_sensible(
    fabrique, cfg
):
    import re

    from amundi_agentic.llm import LLMConfig

    brute = LLMConfig.model_validate(cfg.model_dump())
    assert brute.source_sha256 is None  # construite sans load_config
    h = fabrique(config=brute).run_fields()["llm_config_sha256"]
    assert isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)
    # déterministe : même config, même hash (y compris pour une autre instance et un autre client)
    autre = LLMConfig.model_validate(cfg.model_dump())
    assert fabrique(config=autre).run_fields()["llm_config_sha256"] == h
    assert fabrique(config=brute).run_fields()["llm_config_sha256"] == h
    # sensible à un changement de configuration
    modif = cfg.model_dump()
    modif["defaults"]["temperature"] = 0.5
    h2 = fabrique(config=LLMConfig.model_validate(modif)).run_fields()["llm_config_sha256"]
    assert h2 != h and re.fullmatch(r"[0-9a-f]{64}", h2)
    modif2 = cfg.model_dump()
    modif2["evaluation"]["models"]["main"] = "gemini/gemini-0.0-flash"
    h3 = fabrique(config=LLMConfig.model_validate(modif2)).run_fields()["llm_config_sha256"]
    assert h3 not in (h, h2)
    # le RunRecord construit avec ce hash est valide
    c = fabrique(config=brute)
    assert run_record(c).llm_config_sha256 == h
    ev = fabrique(config=brute, mode="evaluation")
    ev.complete(MSG, date_donnees=T)
    assert run_record(ev).llm_config_sha256 == h
