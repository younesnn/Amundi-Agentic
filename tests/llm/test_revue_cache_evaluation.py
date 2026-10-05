"""Revue indépendante : cache x mode évaluation (D-024, EX-NF-13), reprise, fichier du modèle figé,
cloisonnement par mode et profil, garde `_entree_acceptable`, profil d'évaluation.

Chaque protection du cache (clé cloisonnée par `scope`, garde `_entree_acceptable`) est testée
SÉPARÉMENT : on neutralise l'une par `monkeypatch` et l'autre doit suffire.
"""

import json
import os
import subprocess
import sys
from datetime import date

import pytest

from amundi_agentic.llm import (
    ConfigurationError,
    ExecutionPausee,
    LLMClient,
    LLMConfig,
    MockLLMClient,
    ModeleServiChange,
    ProviderError,
    load_config,
)
from amundi_agentic.llm.cache import DiskCache, cache_key
from amundi_agentic.llm.types import FichierFigeCorrompu, LLMError, RawCompletion

T = date(2024, 2, 1)
MSG = [{"role": "user", "content": "Bonjour"}]


def msg(i):
    return [{"role": "user", "content": f"question {i}"}]


def chemin_entree(cache_dir, cle):
    return next(cache_dir.rglob(f"{cle}.json"))


# --------------------------------------------------------------------------- config (1c)


def _eval(cfg, **modeles):
    return {
        "evaluation": {
            "fallback_enabled": False,
            "models": {**cfg.evaluation.models, **modeles},
        }
    }


@pytest.mark.parametrize("niveau", ["main", "light"])
@pytest.mark.parametrize("source", ["main", "light", "fallback", "dev"])
def test_config_refuse_un_identifiant_d_evaluation_qui_coincide_avec_models(cfg, niveau, source):
    with pytest.raises(ConfigurationError, match="coïncide|figée"):
        load_config(overrides=_eval(cfg, **{niveau: cfg.models[source]}))


@pytest.mark.parametrize(
    "ident", ["gemini/gemini-9-flash-latest", "gemini/X-LATEST", "gemini/gemini-9-Latest"]
)
def test_config_refuse_latest_dans_les_identifiants_d_evaluation(cfg, ident):
    with pytest.raises(ConfigurationError, match="figée"):
        load_config(overrides=_eval(cfg, main=ident))


def test_config_accepte_un_identifiant_fige_distinct(cfg):
    ok = load_config(overrides=_eval(cfg, main="gemini/gemini-9.9-flash"))
    assert ok.evaluation.models["main"] == "gemini/gemini-9.9-flash"


def test_config_toute_erreur_de_validation_devient_configuration_error(cfg):
    with pytest.raises(ConfigurationError):
        load_config(overrides={"champ_inconnu": 1})
    with pytest.raises(ConfigurationError):
        load_config(overrides={"retry": {"max_attempts": 0}})
    assert issubclass(ConfigurationError, ValueError)  # compatibilité avec les appelants


def test_config_hash_de_la_source_calcule_par_load_config_et_non_falsifiable(tmp_path):
    import hashlib
    import shutil

    from amundi_agentic.llm.config import CONFIG_PATH

    assert load_config().source_sha256 == hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    copie = tmp_path / "llm.yaml"
    shutil.copy(CONFIG_PATH, copie)
    copie.write_text(copie.read_text() + '\nsource_sha256: "' + "0" * 64 + '"\n')
    c = load_config(copie)
    assert c.source_sha256 == hashlib.sha256(copie.read_bytes()).hexdigest() != "0" * 64
    assert "source_sha256" not in c.model_dump()


# --------------------------------------------------------------------------- point 1 : cache


def test_l_entree_du_cache_porte_le_modele_servi_et_le_relais(fabrique, cfg, tmp_path):
    c = fabrique()
    c.mock.fail("quota", 1, model=cfg.models["main"])
    r = c.complete(MSG, date_donnees=T)
    entree = json.loads(next((tmp_path / "cache").rglob("*.json")).read_text())
    assert entree["modele_servi"] == r.record.modele_servi
    assert entree["relais_utilise"] is True
    assert entree["modele_demande"] == cfg.models["fallback"]


def test_entree_du_profil_dev_jamais_servie_a_une_requete_prod(fabrique, cfg):
    dev = fabrique(profile="dev")
    dev.complete(MSG, date_donnees=T)
    prod = fabrique(profile="prod")
    r = prod.complete(MSG, date_donnees=T)
    assert prod.mock.chat_calls, "la requête prod a été servie par le cache du profil dev"
    assert r.record.cache_hit is False and r.record.modele_demande == cfg.models["main"]


def test_entree_prod_jamais_servie_au_profil_dev(fabrique, cfg):
    prod = fabrique(profile="prod")
    prod.complete(MSG, date_donnees=T)
    dev = fabrique(profile="dev")
    r = dev.complete(MSG, date_donnees=T)
    assert dev.mock.chat_calls and r.record.cache_hit is False
    assert r.record.modele_demande == cfg.models["dev"]


def test_entree_relayee_interactive_jamais_servie_en_evaluation_config_reelle(fabrique, cfg):
    inter = fabrique(mode="interactif")
    inter.mock.fail("quota", 1, model=cfg.models["main"])
    relayee = inter.complete(MSG, date_donnees=T)
    assert relayee.record.relais_utilise
    ev = fabrique(mode="evaluation")
    r = ev.complete(MSG, date_donnees=T)
    assert r.record.cache_hit is False
    assert r.record.modele_demande == cfg.evaluation.models["main"]
    assert ev.modeles_servis_figes == {"main": cfg.evaluation.models["main"].split("/", 1)[1]}


def test_cles_de_cache_interactif_et_evaluation_distinctes_dans_la_config_reelle(fabrique, cfg):
    a = fabrique(mode="interactif").complete(MSG, date_donnees=T).record.cle_cache
    b = fabrique(mode="evaluation").complete(MSG, date_donnees=T).record.cle_cache
    assert a != b


@pytest.fixture
def meme_modele_partout(monkeypatch, cfg):
    """Simule un recouvrement d'identifiants (que `load_config` interdit désormais) : toutes les
    chaînes se réduisent au même modèle. Seuls `scope` et la garde peuvent alors cloisonner."""
    modele = cfg.models["main"]
    monkeypatch.setattr(
        LLMConfig, "chain", lambda self, tier, *, mode, profile: [("main", modele)], raising=True
    )
    return modele


def test_scope_distingue_mode_et_profil_meme_avec_un_modele_commun(fabrique, meme_modele_partout):
    cles = {}
    for mode, profil in [
        ("interactif", "prod"),
        ("interactif", "dev"),
        ("evaluation", "prod"),
    ]:
        r = fabrique(mode=mode, profile=profil).complete(MSG, date_donnees=T)
        cles[(mode, profil)] = r.record.cle_cache
    assert len(set(cles.values())) == 3


def _entree_relayee_a_la_main(cache_dir, cle, modele_groq):
    """Transforme l'entrée de `cle` en réponse produite par le relais Groq."""
    chemin = chemin_entree(cache_dir, cle)
    e = json.loads(chemin.read_text())
    e.update(
        modele_servi="openai/gpt-oss-120b",
        modele_demande=modele_groq,
        fournisseur="groq",
        tier="fallback",
        relais_utilise=True,
        text='{"origine": "relais"}',
    )
    chemin.write_text(json.dumps(e))


def _scenario_relais(fabrique, cfg, monkeypatch, *, sans_scope, sans_garde):
    modele = cfg.models["main"]
    monkeypatch.setattr(
        LLMConfig, "chain", lambda self, tier, *, mode, profile: [("main", modele)], raising=True
    )
    if sans_scope:
        monkeypatch.setattr(LLMClient, "_scope", property(lambda self: ""))
    if sans_garde:
        monkeypatch.setattr(
            LLMClient, "_entree_acceptable", lambda self, entree, demande, champ: champ in entree
        )
    inter = fabrique(mode="interactif")
    rec_inter = inter.complete(MSG, date_donnees=T).record
    _entree_relayee_a_la_main(inter.cache.directory, rec_inter.cle_cache, cfg.models["fallback"])
    ev = fabrique(mode="evaluation")
    r = ev.complete(MSG, date_donnees=T)
    return rec_inter, ev, r


def test_entree_relayee_non_servie_en_evaluation_grace_au_scope_seul(
    fabrique, cfg, monkeypatch, meme_modele_partout
):
    monkeypatch.undo()  # `meme_modele_partout` est refait par le scénario
    rec_inter, ev, r = _scenario_relais(
        fabrique, cfg, monkeypatch, sans_scope=False, sans_garde=True
    )
    assert r.record.cle_cache != rec_inter.cle_cache  # clé cloisonnée par mode/profil
    assert r.record.cache_hit is False and len(ev.mock.chat_calls) == 1
    assert r.text != '{"origine": "relais"}' and r.record.relais_utilise is False


def test_entree_relayee_non_servie_en_evaluation_grace_a_la_garde_seule(fabrique, cfg, monkeypatch):
    rec_inter, ev, r = _scenario_relais(
        fabrique, cfg, monkeypatch, sans_scope=True, sans_garde=False
    )
    assert r.record.cle_cache == rec_inter.cle_cache  # le scope est bien neutralisé
    assert r.record.cache_hit is False and len(ev.mock.chat_calls) == 1
    assert r.text != '{"origine": "relais"}' and r.record.relais_utilise is False
    assert ev.modeles_servis_figes == {"main": cfg.models["main"].split("/", 1)[1]}
    # la bonne réponse a remplacé l'entrée relayée
    assert (
        json.loads(chemin_entree(ev.cache.directory, r.record.cle_cache).read_text())[
            "relais_utilise"
        ]
        is False
    )


def test_sans_aucune_des_deux_protections_le_melange_n_est_arrete_que_par_le_validateur(
    fabrique, cfg, monkeypatch
):
    """Preuve de sensibilité des deux tests précédents : sans scope ni garde, la réponse relayée
    est lue en évaluation ; seul le validateur d'`ExecutionRecord` (aucun relais en évaluation)
    arrête alors l'exécution, par une erreur brute (filet de sécurité, pas un mécanisme prévu)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="aucun relais"):
        _scenario_relais(fabrique, cfg, monkeypatch, sans_scope=True, sans_garde=True)


def test_garde_refuse_un_autre_modele_demande_en_evaluation(fabrique, cfg):
    a = fabrique(mode="evaluation")
    rec = a.complete(MSG, date_donnees=T).record
    chemin = chemin_entree(a.cache.directory, rec.cle_cache)
    e = json.loads(chemin.read_text())
    e["modele_demande"] = "gemini/un-autre-modele"
    chemin.write_text(json.dumps(e))
    b = fabrique(mode="evaluation")
    r = b.complete(MSG, date_donnees=T)
    assert r.record.cache_hit is False and len(b.mock.chat_calls) == 1


@pytest.mark.parametrize("champ", ["text", "modele_servi", "modele_demande"])
def test_garde_refuse_une_entree_sans_champ_attendu_en_evaluation(fabrique, champ):
    a = fabrique(mode="evaluation")
    rec = a.complete(MSG, date_donnees=T).record
    chemin = chemin_entree(a.cache.directory, rec.cle_cache)
    e = json.loads(chemin.read_text())
    del e[champ]
    chemin.write_text(json.dumps(e))
    b = fabrique(mode="evaluation")
    try:
        r = b.complete(MSG, date_donnees=T)
    except ModeleServiChange:
        assert champ == "modele_servi"  # refus explicite (modèle servi absent) : acceptable
        return
    assert r.record.cache_hit is False  # entrée ignorée et relue


def test_garde_refuse_une_entree_embedding_sans_vecteurs(fabrique):
    a = fabrique(mode="evaluation")
    a.embed(["a"], date_donnees=T)
    chemin = next(a.cache.directory.rglob("*.json"))
    e = json.loads(chemin.read_text())
    del e["vectors"]
    chemin.write_text(json.dumps(e))
    b = fabrique(mode="evaluation")
    r = b.embed(["a"], date_donnees=T)
    assert r.record.cache_hit is False and len(b.mock.calls) == 1


def test_garde_refuse_un_embedding_relaye_en_evaluation(fabrique):
    a = fabrique(mode="evaluation")
    rec = a.embed(["a"], date_donnees=T).record
    chemin = chemin_entree(a.cache.directory, rec.cle_cache)
    e = json.loads(chemin.read_text())
    e["relais_utilise"] = True
    chemin.write_text(json.dumps(e))
    b = fabrique(mode="evaluation")
    assert b.embed(["a"], date_donnees=T).record.cache_hit is False


def test_mode_interactif_accepte_une_entree_relayee_et_le_journal_le_dit(fabrique, cfg, tmp_path):
    a = fabrique(run_dir=tmp_path / "ra")
    a.mock.fail("quota", 1, model=cfg.models["main"])
    a.complete(MSG, date_donnees=T)
    b = fabrique(run_dir=tmp_path / "rb")
    r = b.complete(MSG, date_donnees=T)
    assert r.record.cache_hit and r.record.relais_utilise is True
    ligne = json.loads((tmp_path / "rb" / "calls.jsonl").read_text().splitlines()[-1])
    assert ligne["relais_utilise"] is True and ligne["cache_hit"] is True


def test_relais_utilise_dans_calls_jsonl_ne_ment_jamais(fabrique, cfg, tmp_path):
    inter = fabrique(run_dir=tmp_path / "ri")
    inter.mock.fail("quota", 1, model=cfg.models["main"])
    inter.complete(MSG, date_donnees=T)
    inter.mock.fail("quota", 1, model=cfg.models["main"])
    inter.complete(msg(2), date_donnees=T)
    lignes = [json.loads(x) for x in (tmp_path / "ri" / "calls.jsonl").read_text().splitlines()]
    reussis = [x for x in lignes if x["erreur"] is None]
    assert reussis and all(x["relais_utilise"] is (x["fournisseur"] == "groq") for x in reussis)
    ev = fabrique(mode="evaluation", run_dir=tmp_path / "re")
    ev.complete(MSG, date_donnees=T)
    ev.complete(MSG, date_donnees=T)  # cache hit
    lignes = [json.loads(x) for x in (tmp_path / "re" / "calls.jsonl").read_text().splitlines()]
    assert lignes and not any(x["relais_utilise"] for x in lignes)
    assert {x["mode"] for x in lignes} == {"evaluation"}


def test_evaluation_entree_de_cache_sans_modele_servi_refusee(fabrique, cfg):
    ev = fabrique(mode="evaluation")
    r = ev.complete(MSG, date_donnees=T)
    chemin = chemin_entree(ev.cache.directory, r.record.cle_cache)
    entree = json.loads(chemin.read_text())
    del entree["modele_servi"]
    chemin.write_text(json.dumps(entree))
    ev2 = fabrique(mode="evaluation")
    try:
        ev2.complete(MSG, date_donnees=T)
    except ModeleServiChange:
        return
    assert ev2.mock.chat_calls  # sinon : entrée ignorée et relue, jamais servie sans modèle


def test_evaluation_cache_d_abord_puis_appel_reel_a_version_differente_arrete(fabrique, cfg):
    modele = cfg.evaluation.models["main"]
    a = fabrique(mode="evaluation")
    a.mock.set_served(modele, "v1")
    a.complete(MSG, date_donnees=T)
    b = fabrique(mode="evaluation")
    b.mock.set_served(modele, "v2")
    b.complete(MSG, date_donnees=T)  # cache : gèle v1
    assert b.modeles_servis_figes == {"main": "v1"}
    with pytest.raises(ModeleServiChange):
        b.complete(MSG, date_donnees=date(2024, 2, 2))  # appel réel servi par v2


def test_niveaux_main_et_light_geles_independamment(fabrique, cfg, tmp_path):
    ev = fabrique(mode="evaluation", run_dir=tmp_path / "r")
    ev.mock.set_served(cfg.evaluation.models["main"], "M1")
    ev.mock.set_served(cfg.evaluation.models["light"], "L1")
    ev.complete(MSG, date_donnees=T, tier="main")
    ev.complete(MSG, date_donnees=T, tier="light")
    assert ev.modeles_servis_figes == {"main": "M1", "light": "L1"}
    assert json.loads((tmp_path / "r" / "modele_servi_fige.json").read_text()) == {
        "main": "M1",
        "light": "L1",
    }
    ev.mock.set_served(cfg.evaluation.models["light"], "L2")
    with pytest.raises(ModeleServiChange):
        ev.complete(msg(2), date_donnees=T, tier="light")
    ev.complete(msg(3), date_donnees=T, tier="main")  # main n'a pas dérivé


def test_evaluation_niveau_sans_modele_fige_refuse(fabrique):
    ev = fabrique(mode="evaluation")
    with pytest.raises(ConfigurationError):
        ev.complete(MSG, date_donnees=T, tier="fallback")


# --------------------------------------------------------------------------- profil


def test_evaluation_sans_profil_explicite_utilise_le_modele_fige(cfg, tmp_path):
    c = MockLLMClient(
        cfg, mode="evaluation", cache_dir=tmp_path / "c", quota_journal=tmp_path / "q"
    )
    r = c.complete(MSG, date_donnees=T)
    assert c.profile == "prod"
    assert [a["model"] for a in c.mock.chat_calls] == [cfg.evaluation.models["main"]]
    assert r.record.modele_demande == cfg.evaluation.models["main"]
    assert r.record.modele_demande != cfg.models["dev"]


def test_evaluation_refuse_le_profil_dev(cfg, tmp_path):
    with pytest.raises(ConfigurationError, match="prod"):
        MockLLMClient(
            cfg,
            mode="evaluation",
            profile="dev",
            cache_dir=tmp_path / "c",
            quota_journal=tmp_path / "q",
        )


def test_evaluation_profil_dev_refuse_aussi_quand_la_config_par_defaut_est_dev(cfg, tmp_path):
    assert cfg.default_mode == "dev"
    with pytest.raises(ConfigurationError):
        LLMClient(cfg, mode="evaluation", profile="dev", transport=object())


def test_interactif_garde_le_profil_par_defaut_de_la_config(cfg, tmp_path):
    c = MockLLMClient(cfg, cache_dir=tmp_path / "c", quota_journal=tmp_path / "q")
    assert c.profile == cfg.default_mode
    p = MockLLMClient(cfg, profile="prod", cache_dir=tmp_path / "c", quota_journal=tmp_path / "q")
    assert p.profile == "prod"


# --------------------------------------------------------------------------- reprise


def test_reprise_apres_pause_ne_refait_aucun_appel_deja_fait(fabrique, cfg, tmp_path):
    run = tmp_path / "run"
    a = fabrique(mode="evaluation", run_dir=run)
    for i in range(3):
        a.complete(msg(i), date_donnees=T)
    a.mock.fail("quota", cfg.retry.pause_429_max_waits + 1)
    with pytest.raises(ExecutionPausee):
        a.complete(msg(3), date_donnees=T)
    b = fabrique(mode="evaluation", run_dir=run)
    for i in range(4):
        r = b.complete(msg(i), date_donnees=T)
        assert r.record.cache_hit is (i < 3)
    assert len(b.mock.chat_calls) == 1
    assert b.usage()["cache_hits"] == 3 and b.usage()["appels"] == 1
    lignes = (run / "calls.jsonl").read_text().splitlines()
    assert any(json.loads(x)["cache_hit"] for x in lignes)


def test_la_pause_ne_met_rien_en_cache(fabrique, cfg):
    ev = fabrique(mode="evaluation")
    ev.mock.fail("quota", cfg.retry.pause_429_max_waits + 1)
    with pytest.raises(ExecutionPausee):
        ev.complete(MSG, date_donnees=T)
    assert not list(ev.cache.directory.rglob("*.json"))


@pytest.mark.parametrize("kind", ["unavailable", "timeout"])
def test_evaluation_503_et_timeout_reessayes_puis_pause_sans_relais(fabrique, cfg, kind):
    ev = fabrique(mode="evaluation")
    ev.mock.fail(kind, cfg.retry.max_attempts)
    with pytest.raises(ExecutionPausee) as e:
        ev.complete(MSG, date_donnees=T)
    assert e.value.kind == kind
    assert len(ev.mock.chat_calls) == cfg.retry.max_attempts
    assert {c["model"] for c in ev.mock.chat_calls} == {cfg.evaluation.models["main"]}
    attendus = [
        min(cfg.retry.backoff_base_s * cfg.retry.backoff_factor**i, cfg.retry.backoff_max_s)
        for i in range(cfg.retry.max_attempts - 1)
    ]
    assert ev.sleeps == attendus


def test_evaluation_erreur_d_authentification_ni_pause_ni_relais(fabrique):
    ev = fabrique(mode="evaluation")
    ev.mock.push(ProviderError("auth", "401", 401))
    with pytest.raises(ProviderError):
        ev.complete(MSG, date_donnees=T)
    assert len(ev.mock.chat_calls) == 1 and ev.sleeps == []


def test_evaluation_embeddings_sans_relais_et_modele_servi_controle(fabrique, cfg):
    ev = fabrique(mode="evaluation")
    ev.embed(["a"], date_donnees=T)
    assert ev.modeles_servis_figes.get("embed")
    ev.mock.set_served(cfg.embedding_model("prod"), "autre-version")
    with pytest.raises(ModeleServiChange):
        ev.embed(["b"], date_donnees=T)


# ------------------------------------------------------------------- ExecutionRecord sur arrêt


def test_execution_record_ecrit_quand_le_modele_servi_change_appel_reel(fabrique, cfg, tmp_path):
    modele = cfg.evaluation.models["main"]
    ev = fabrique(mode="evaluation", run_dir=tmp_path / "run")
    ev.mock.set_served(modele, "v1")
    ev.complete(MSG, date_donnees=T)
    ev.mock.set_served(modele, "v2")
    with pytest.raises(ModeleServiChange):
        ev.complete(msg(2), date_donnees=T)
    rec = ev.records[-1]
    assert rec.erreur and rec.erreur.startswith("modele_servi_change")
    assert rec.modele_servi == "v2" and rec.cache_hit is False and rec.tier_demande == "main"
    assert rec.tokens_entree > 0
    derniere = json.loads((tmp_path / "run" / "calls.jsonl").read_text().splitlines()[-1])
    assert derniere["erreur"].startswith("modele_servi_change") and derniere["modele_servi"] == "v2"
    assert ev.usage()["erreurs"] == 1


def test_execution_record_ecrit_quand_le_modele_servi_change_cache_hit(fabrique, cfg, tmp_path):
    modele = cfg.evaluation.models["main"]
    a = fabrique(mode="evaluation")
    a.mock.set_served(modele, "v1")
    a.complete(MSG, date_donnees=T)
    b = fabrique(mode="evaluation", run_dir=tmp_path / "run")
    b.mock.set_served(modele, "v2")
    b.complete(msg(9), date_donnees=T)  # gèle v2
    with pytest.raises(ModeleServiChange):
        b.complete(MSG, date_donnees=T)  # entrée v1 du cache
    rec = b.records[-1]
    assert rec.cache_hit is True and rec.erreur.startswith("modele_servi_change")
    assert rec.modele_servi == "v1" and rec.relais_utilise is False
    lignes = (tmp_path / "run" / "calls.jsonl").read_text().splitlines()
    assert json.loads(lignes[-1])["cache_hit"] is True


def test_tier_demande_toujours_renseigne(fabrique, cfg, tmp_path):
    c = fabrique(run_dir=tmp_path / "run")
    c.mock.fail("quota", 1, model=cfg.models["main"])
    c.mock.fail("unavailable", 1, model=cfg.models["fallback"])
    r = c.complete(MSG, date_donnees=T, tier="main")
    assert r.record.tier == "fallback" and r.record.tier_demande == "main"
    c.complete(msg(2), date_donnees=T, tier="light")
    c.complete(msg(2), date_donnees=T, tier="light")  # cache hit
    c.embed(["x"], date_donnees=T)
    assert [x.tier_demande for x in c.records if x.erreur is None] == [
        "main",
        "light",
        "light",
        "embed",
    ]
    assert all(x.tier_demande for x in c.records)  # y compris les enregistrements d'erreur
    dev = fabrique(profile="dev")
    assert dev.complete(MSG, date_donnees=T, tier="light").record.tier_demande == "light"


# --------------------------------------------------------------------------- fichier figé

FIGES_INVALIDES = [
    ("vide", ""),
    ("json invalide", "{corrompu"),
    ("liste", "[1, 2]"),
    ("chaine", '"main"'),
    ("nul", "null"),
    ("valeur non chaine", '{"main": 3}'),
    ("valeur nulle", '{"main": null}'),
    ("valeur vide", '{"main": ""}'),
    ("valeur objet", '{"main": {"a": 1}}'),
    ("valeur liste", '{"main": ["v"]}'),
]


@pytest.mark.parametrize(
    "contenu", [c for _, c in FIGES_INVALIDES], ids=[n for n, _ in FIGES_INVALIDES]
)
def test_fichier_fige_invalide_arrete_la_construction_du_client_en_evaluation(
    fabrique, tmp_path, contenu
):
    run = tmp_path / "run"
    run.mkdir()
    (run / "modele_servi_fige.json").write_text(contenu)
    with pytest.raises(FichierFigeCorrompu) as e:
        fabrique(mode="evaluation", run_dir=run)
    assert isinstance(e.value, LLMError) and not isinstance(e.value, TypeError)
    assert (run / "modele_servi_fige.json").read_text() == contenu  # jamais réécrit


def test_fichier_fige_binaire_arrete_le_client(fabrique, tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "modele_servi_fige.json").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(FichierFigeCorrompu):
        fabrique(mode="evaluation", run_dir=run)


def test_fichier_fige_valide_vide_ou_complet_accepte(fabrique, tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "modele_servi_fige.json").write_text("{}")
    assert fabrique(mode="evaluation", run_dir=run).modeles_servis_figes == {}
    (run / "modele_servi_fige.json").write_text('{"main": "v1", "light": "l1"}')
    assert fabrique(mode="evaluation", run_dir=run).modeles_servis_figes == {
        "main": "v1",
        "light": "l1",
    }


def test_fichier_fige_corrompu_ignore_en_interactif_qui_ne_gele_rien(fabrique, tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "modele_servi_fige.json").write_text("{corrompu")
    c = fabrique(mode="interactif", run_dir=run)
    c.complete(MSG, date_donnees=T)
    assert c.modeles_servis_figes == {}


def test_fichier_fige_corrompu_message_sans_contenu_du_fichier(fabrique, tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "modele_servi_fige.json").write_text('{"main": 3, "secret": "AIza' + "x" * 30 + '"}')
    with pytest.raises(FichierFigeCorrompu) as e:
        fabrique(mode="evaluation", run_dir=run)
    assert "AIza" not in str(e.value)


def test_fichier_fige_modifie_entre_deux_reprises_arrete_le_run(fabrique, cfg, tmp_path):
    run = tmp_path / "run"
    a = fabrique(mode="evaluation", run_dir=run)
    a.complete(MSG, date_donnees=T)
    (run / "modele_servi_fige.json").write_text(json.dumps({"main": "falsifie"}))
    b = fabrique(mode="evaluation", run_dir=run)
    assert b.modeles_servis_figes == {"main": "falsifie"}
    with pytest.raises(ModeleServiChange):
        b.complete(msg(2), date_donnees=T)  # appel réel servi par la vraie version


def _interrompre_remplacement_du_fichier_fige(monkeypatch):
    vrai = os.replace

    def faux(src, dst, *a, **k):
        if str(dst).endswith("modele_servi_fige.json"):
            raise KeyboardInterrupt
        return vrai(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", faux)


def test_ecriture_du_fichier_fige_atomique_premiere_ecriture_interrompue(
    fabrique, tmp_path, monkeypatch
):
    run = tmp_path / "run"
    ev = fabrique(mode="evaluation", run_dir=run)
    _interrompre_remplacement_du_fichier_fige(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        ev.complete(MSG, date_donnees=T)
    monkeypatch.undo()
    assert not (run / "modele_servi_fige.json").exists()
    assert not list(run.glob(".tmp-*"))
    # la reprise ne voit ni fichier partiel ni erreur
    fabrique(mode="evaluation", run_dir=run).complete(MSG, date_donnees=T)
    json.loads((run / "modele_servi_fige.json").read_text())


def test_ecriture_du_fichier_fige_atomique_ancien_contenu_preserve(
    fabrique, cfg, tmp_path, monkeypatch
):
    run = tmp_path / "run"
    ev = fabrique(mode="evaluation", run_dir=run)
    ev.complete(MSG, date_donnees=T, tier="main")
    avant = (run / "modele_servi_fige.json").read_text()
    _interrompre_remplacement_du_fichier_fige(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        ev.complete(MSG, date_donnees=T, tier="light")  # gèlerait le niveau light
    monkeypatch.undo()
    assert (run / "modele_servi_fige.json").read_text() == avant
    assert not list(run.glob(".tmp-*"))
    fabrique(mode="evaluation", run_dir=run)  # fichier toujours lisible


# --------------------------------------------------------------------------- clé de cache


def test_cle_de_cache_inclut_la_date_de_donnee(fabrique):
    c = fabrique()
    a = c.complete(MSG, date_donnees=date(2024, 2, 1))
    b = c.complete(MSG, date_donnees=date(2024, 2, 2))
    assert a.record.cle_cache != b.record.cle_cache and b.record.cache_hit is False


def test_cache_key_distingue_chaque_composante():
    base = dict(
        kind="chat",
        model="m",
        messages=[{"role": "user", "content": "x"}],
        schema=None,
        params={"temperature": 0, "seed": 0, "max_tokens": None},
        date_donnees=T,
        scope="interactif/prod",
    )
    ref = cache_key(**base)
    variantes = [
        {"kind": "embed"},
        {"model": "m2"},
        {"messages": [{"role": "user", "content": "y"}]},
        {"schema": {"a": 1}},
        {"params": {"temperature": 0.1, "seed": 0, "max_tokens": None}},
        {"params": {"temperature": 0, "seed": 1, "max_tokens": None}},
        {"params": {"temperature": 0, "seed": 0, "max_tokens": 5}},
        {"date_donnees": date(2024, 2, 2)},
        {"scope": "evaluation/prod"},
        {"scope": "interactif/dev"},
        {"scope": ""},
    ]
    cles = {cache_key(**{**base, **v}) for v in variantes}
    assert ref not in cles and len(cles) == len(variantes)


def test_cache_key_stable_entre_processus_avec_scope():
    code = (
        "from datetime import date; from amundi_agentic.llm.cache import cache_key;"
        "print(cache_key(kind='chat', model='m', messages=[{'role':'user','content':'é'}],"
        "schema=None, params={'seed':0}, date_donnees=date(2024,2,1), scope='evaluation/prod'))"
    )
    sorties = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": str(s)},
        ).stdout
        for s in (1, 2, 3)
    }
    assert len(sorties) == 1


# --------------------------------------------------------------------------- interruption


def test_interruption_pendant_l_ecriture_du_cache_ne_laisse_ni_entree_ni_temporaire(
    tmp_path, monkeypatch
):
    cache = DiskCache(tmp_path / "c")

    def interrompu(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrompu)
    with pytest.raises(KeyboardInterrupt):
        cache.put("ab" + "0" * 62, {"text": "x"})
    monkeypatch.undo()
    assert cache.get("ab" + "0" * 62) is None
    assert not list((tmp_path / "c").rglob(".tmp-*"))


def test_entree_de_cache_binaire_traitee_comme_absente(tmp_path):
    cache = DiskCache(tmp_path / "c")
    cle = "cd" + "1" * 62
    cache.put(cle, {"text": "x"})
    chemin = next((tmp_path / "c").rglob("*.json"))
    chemin.write_bytes(b"\xff\xfe\x00bad")
    assert cache.get(cle) is None


@pytest.mark.parametrize("contenu", ["[1, 2]", "3", '"texte"', "null", "true", "1.5", "[]", "{"])
def test_diskcache_get_renvoie_none_pour_toute_entree_qui_n_est_pas_un_dict(tmp_path, contenu):
    cache = DiskCache(tmp_path / "c")
    cle = "ef" + "2" * 62
    cache.put(cle, {"text": "x"})
    next((tmp_path / "c").rglob("*.json")).write_text(contenu)
    assert cache.get(cle) is None
    assert cle not in cache


def test_entree_non_dict_dans_le_cache_est_rappelee_par_le_client(fabrique):
    c = fabrique()
    rec = c.complete(MSG, date_donnees=T).record
    chemin_entree(c.cache.directory, rec.cle_cache).write_text("[1, 2]")
    c2 = fabrique()
    r = c2.complete(MSG, date_donnees=T)
    assert r.record.cache_hit is False and len(c2.mock.chat_calls) == 1


def test_sortie_invalide_jamais_en_cache_et_raw_inconnu(fabrique):
    c = fabrique()
    c.mock.push(RawCompletion("{}", "v"))
    c.complete(MSG, date_donnees=T)
    assert len(list(c.cache.directory.rglob("*.json"))) == 1
