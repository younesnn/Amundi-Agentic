"""LLMClient en mode interactif, avec LLM simulé : cache, relais, nouvelles tentatives,
sorties structurées, embeddings, agnosticisme (EX-NF-03, 04, 05, 10, 14)."""

import json
from datetime import date

import pytest
from pydantic import BaseModel

from amundi_agentic.llm import (
    ConfigurationError,
    LLMClient,
    MockLLMClient,
    ProviderError,
    QuotaEpuise,
    StructuredOutputError,
    load_config,
)
from amundi_agentic.llm.mock import MockTransport

T = date(2024, 2, 1)
MSG = [{"role": "system", "content": "Tu es un test."}, {"role": "user", "content": "Bonjour"}]


class Reponse(BaseModel):
    x: int
    ok: bool = True


# --------------------------------------------------------------------------- bases


def test_complete_renvoie_texte_et_enregistrement(fabrique, cfg):
    c = fabrique(responses=["bonjour"])
    r = c.complete(MSG, date_donnees=T, agent="macro")
    assert r.text == "bonjour"
    assert r.record.modele_demande == cfg.models["main"]
    assert r.record.tier == "main"
    assert r.record.mode == "interactif"
    assert r.record.agent == "macro"
    assert r.record.relais_utilise is False and r.record.cache_hit is False
    assert r.record.cout_eur == 0 and r.record.tokens_entree > 0


def test_temperature_zero_et_graine_enregistrees(fabrique, cfg):
    c = fabrique(seed=7)
    r = c.complete(MSG, date_donnees=T)
    appel = c.mock.chat_calls[0]
    assert appel["temperature"] == 0 and appel["seed"] == 7
    assert (r.record.temperature, r.record.graine) == (0, 7)
    r2 = c.complete(MSG, date_donnees=T, seed=9, temperature=0.5)
    assert (r2.record.temperature, r2.record.graine) == (0.5, 9)


def test_execution_enregistre_modele_servi_et_hash_du_prompt(fabrique):
    c = fabrique()
    c.mock.set_served(c.config.models["main"], "version-exacte")
    r = c.complete(MSG, date_donnees=T)
    assert r.record.modele_servi == "version-exacte"
    assert len(r.record.prompt_sha256) == 64 and len(r.record.cle_cache) == 64


def test_prompt_ref_enregistre(fabrique):
    from amundi_agentic.llm import PromptRef

    c = fabrique()
    ref = PromptRef(prompt_id="macro", version="1", sha256="c" * 64)
    r = c.complete(MSG, date_donnees=T, prompt_ref=ref)
    assert (r.record.prompt_id, r.record.prompt_version, r.record.prompt_sha256) == (
        "macro",
        "1",
        "c" * 64,
    )


def test_calls_jsonl_en_ajout_seul(fabrique, tmp_path):
    c = fabrique(run_dir=tmp_path / "run", run_id="r1")
    c.complete(MSG, date_donnees=T)
    c.complete(MSG, date_donnees=T)  # servi par le cache, journalisé aussi
    lignes = (tmp_path / "run" / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["cache_hit"] for x in lignes] == [False, True]
    assert json.loads(lignes[0])["run_id"] == "r1"


def test_niveau_inconnu_refuse(fabrique):
    with pytest.raises(ConfigurationError):
        fabrique().complete(MSG, date_donnees=T, tier="inexistant")


# --------------------------------------------------------------------------- cache


def test_requete_identique_servie_par_le_cache(fabrique):
    c = fabrique(responses=["premiere", "seconde"])
    a = c.complete(MSG, date_donnees=T)
    b = c.complete(MSG, date_donnees=T)
    assert (a.text, b.text) == ("premiere", "premiere")
    assert len(c.mock.chat_calls) == 1
    assert b.record.cache_hit and b.record.tokens_entree == 0
    assert c.usage()["cache_hits"] == 1 and c.usage()["appels"] == 1


def test_rejeu_depuis_le_cache_identique_apres_redemarrage(fabrique):
    c1 = fabrique(responses=["reponse figee"])
    r1 = c1.complete(MSG, date_donnees=T)
    c2 = fabrique(responses=["autre chose"])  # nouveau client, même dossier de cache
    r2 = c2.complete(MSG, date_donnees=T)
    assert r2.text == r1.text and c2.mock.chat_calls == []
    assert r2.record.modele_servi == r1.record.modele_servi


@pytest.mark.parametrize(
    "variation",
    [
        {"date_donnees": date(2024, 2, 2)},
        {"seed": 1},
        {"temperature": 0.3},
        {"max_tokens": 10},
        {"tier": "light"},
    ],
)
def test_toute_variation_de_la_requete_change_la_cle(fabrique, variation):
    c = fabrique()
    base = c.complete(MSG, date_donnees=T)
    autre = c.complete(MSG, **{"date_donnees": T, **variation})
    assert autre.record.cle_cache != base.record.cle_cache
    assert len(c.mock.chat_calls) == 2


def test_messages_differents_pas_de_collision(fabrique):
    c = fabrique(handler=lambda m, msgs: msgs[-1]["content"])
    a = c.complete([{"role": "user", "content": "a"}], date_donnees=T)
    b = c.complete([{"role": "user", "content": "b"}], date_donnees=T)
    assert (a.text, b.text) == ("a", "b")


def test_reponse_reutilisee_entre_dates_si_meme_date_donnees(fabrique):
    """EX-NF-04 : un appel RAG est daté par le dépôt, pas par t : un seul appel."""
    c = fabrique()
    depot = date(2023, 11, 3)
    c.complete(MSG, date_donnees=depot, agent="rag")
    c.complete(MSG, date_donnees=depot, agent="rag")
    assert len(c.mock.chat_calls) == 1


def test_entree_de_cache_corrompue_traitee_comme_absente(fabrique, tmp_path):
    c = fabrique(responses=["bon"])
    r = c.complete(MSG, date_donnees=T)
    fichier = next((tmp_path / "cache").rglob(f"{r.record.cle_cache}.json"))
    fichier.write_text("{pas du json", encoding="utf-8")
    c2 = fabrique(responses=["refait"])
    assert c2.complete(MSG, date_donnees=T).text == "refait"


def test_cache_desactivable(fabrique, cfg):
    cfg2 = load_config(overrides={"cache": {"enabled": False}})
    c = fabrique(config=cfg2)
    c.complete(MSG, date_donnees=T)
    c.complete(MSG, date_donnees=T)
    assert len(c.mock.chat_calls) == 2


def test_reprise_apres_interruption(fabrique, cfg):
    """Un backtest interrompu (ici par un 429 persistant en évaluation) reprend sans rejouer."""
    from amundi_agentic.llm import ExecutionPausee

    dates = [date(2024, 2, d) for d in (1, 2, 3)]
    c1 = fabrique(mode="evaluation")
    c1.complete(MSG, date_donnees=dates[0])
    c1.mock.fail("quota", cfg.retry.pause_429_max_waits + 1)
    with pytest.raises(ExecutionPausee):
        c1.complete(MSG, date_donnees=dates[1])
    c2 = fabrique(mode="evaluation")
    for d in dates:
        c2.complete(MSG, date_donnees=d)
    assert c2.usage()["cache_hits"] == 1  # la première date vient du cache
    assert len(c2.mock.chat_calls) == 2  # seules les deux autres partent


# --------------------------------------------------------------------------- relais et reprises


def test_relais_sur_429_simule_en_mode_interactif(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", model=cfg.models["main"])
    r = c.complete(MSG, date_donnees=T)
    assert [a["model"] for a in c.mock.chat_calls] == [cfg.models["main"], cfg.models["fallback"]]
    assert r.record.relais_utilise is True
    assert r.record.tier == "fallback"
    assert r.record.fournisseur == cfg.models["fallback"].split("/")[0]
    assert r.record.modele_demande == cfg.models["fallback"]
    assert c.mock.chat_calls[0]["model"].split("/")[0] != r.record.fournisseur


def test_relais_en_cascade_pour_le_niveau_light(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", model=cfg.models["light"])
    c.mock.fail("quota", model=cfg.models["main"])
    r = c.complete(MSG, date_donnees=T, tier="light")
    assert [a["model"] for a in c.mock.chat_calls] == [
        cfg.models["light"],
        cfg.models["main"],
        cfg.models["fallback"],
    ]
    assert r.record.tier == "fallback"


def test_reponse_relayee_mise_en_cache_sous_la_requete_d_origine(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", model=cfg.models["main"])
    c.complete(MSG, date_donnees=T)
    c.complete(MSG, date_donnees=T)
    assert len(c.mock.chat_calls) == 2  # pas de troisième appel


def test_quota_epuise_sur_toute_la_chaine(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", 2)
    with pytest.raises(QuotaEpuise):
        c.complete(MSG, date_donnees=T)


def test_modele_a_court_de_quota_evite_pendant_le_cooldown(fabrique, cfg):
    t = [0.0]
    c = fabrique(monotonic=lambda: t[0])
    c.mock.fail("quota", model=cfg.models["main"])
    c.complete(MSG, date_donnees=T)
    c.complete(MSG, date_donnees=date(2024, 2, 2))
    modeles = [a["model"] for a in c.mock.chat_calls]
    assert modeles == [cfg.models["main"], cfg.models["fallback"], cfg.models["fallback"]]
    t[0] += cfg.relay.cooldown_s + 1
    c.complete(MSG, date_donnees=date(2024, 2, 3))
    assert c.mock.chat_calls[-1]["model"] == cfg.models["main"]


def test_nouvelle_tentative_sur_503_avec_attente_exponentielle(fabrique, cfg):
    c = fabrique()
    c.mock.fail("unavailable", 2, model=cfg.models["main"])
    r = c.complete(MSG, date_donnees=T)
    r_cfg = cfg.retry
    assert c.sleeps == [r_cfg.backoff_base_s, r_cfg.backoff_base_s * r_cfg.backoff_factor]
    assert r.record.relais_utilise is False
    assert len(c.mock.chat_calls) == 3
    assert {a["model"] for a in c.mock.chat_calls} == {cfg.models["main"]}


def test_attente_plafonnee(fabrique):
    cfg = load_config(overrides={"retry": {"max_attempts": 6, "backoff_max_s": 3}})
    c = fabrique(config=cfg)
    c.mock.fail("timeout", 5, model=cfg.models["main"])
    c.complete(MSG, date_donnees=T)
    assert max(c.sleeps) == 3 and len(c.sleeps) == 5


def test_503_epuise_puis_relais_en_interactif(fabrique, cfg):
    c = fabrique()
    c.mock.fail("unavailable", cfg.retry.max_attempts, model=cfg.models["main"])
    r = c.complete(MSG, date_donnees=T)
    assert r.record.relais_utilise and r.record.tier == "fallback"
    assert len(c.sleeps) == cfg.retry.max_attempts - 1


def test_503_epuise_sans_relais_leve_une_erreur_de_fournisseur(fabrique):
    cfg = load_config(overrides={"relay": {"on_unavailable_exhausted": False}})
    c = fabrique(config=cfg)
    c.mock.fail("unavailable", cfg.retry.max_attempts)
    with pytest.raises(ProviderError) as e:
        c.complete(MSG, date_donnees=T)
    assert e.value.kind == "unavailable"


def test_erreur_d_authentification_ni_reessayee_ni_relayee(fabrique):
    c = fabrique()
    c.mock.push(ProviderError("auth", "clé refusée", 401))
    with pytest.raises(ProviderError):
        c.complete(MSG, date_donnees=T)
    assert len(c.mock.chat_calls) == 1 and c.sleeps == []


def test_echecs_journalises_avec_leur_erreur(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", model=cfg.models["main"])
    c.complete(MSG, date_donnees=T)
    erreurs = [r for r in c.records if r.erreur]
    assert len(erreurs) == 1 and erreurs[0].erreur.startswith("quota")
    assert c.usage()["erreurs"] == 1 and c.usage()["appels"] == 1


# --------------------------------------------------------------------------- sorties structurées


def test_sortie_structuree_validee_par_pydantic(fabrique):
    c = fabrique(responses=['{"x": 3}'])
    r = c.complete_structured(Reponse, MSG, date_donnees=T)
    assert r.parsed == Reponse(x=3, ok=True)
    assert c.mock.chat_calls[0]["json_mode"] is True
    # Le schéma est transmis au modèle dans le message système, sans toucher au cache d'origine.
    assert "JSON Schema" in c.mock.chat_calls[0]["messages"][0]["content"]


def test_sortie_structuree_tolere_les_cloture_de_code(fabrique):
    c = fabrique(responses=['Voici :\n```json\n{"x": 1}\n```'])
    assert c.complete_structured(Reponse, MSG, date_donnees=T).parsed.x == 1


def test_json_invalide_puis_valide(fabrique):
    c = fabrique(responses=["pas du json", '{"x": 2}'])
    r = c.complete_structured(Reponse, MSG, date_donnees=T)
    assert r.parsed.x == 2
    assert len(c.mock.chat_calls) == 2 and len(r.attempts) == 1
    # La nouvelle tentative rappelle l'erreur de validation, sans clé ni donnée brute en plus.
    dernier = c.mock.chat_calls[1]["messages"][-1]["content"]
    assert "invalide" in dernier
    # La sortie invalide n'est pas mise en cache : seule la bonne l'est.
    c2 = fabrique(responses=["x"])
    assert c2.complete_structured(Reponse, MSG, date_donnees=T).parsed.x == 2
    assert c2.mock.chat_calls == []


def test_json_invalide_apres_les_tentatives_autorisees(fabrique, cfg):
    c = fabrique(default_text="toujours faux")
    with pytest.raises(StructuredOutputError) as e:
        c.complete_structured(Reponse, MSG, date_donnees=T)
    assert len(c.mock.chat_calls) == cfg.defaults.structured_retries + 1
    assert e.value.last_text == "toujours faux"


def test_champ_manquant_ou_de_mauvais_type_rejete(fabrique):
    c = fabrique(responses=['{"x": "pas un entier"}', '{"ok": true}', '{"x": 5}'])
    assert c.complete_structured(Reponse, MSG, date_donnees=T).parsed.x == 5


def test_schema_entre_dans_la_cle_de_cache(fabrique):
    class Autre(BaseModel):
        y: int

    c = fabrique(responses=['{"x": 1}', '{"y": 2}'])
    assert c.complete_structured(Reponse, MSG, date_donnees=T).parsed.x == 1
    assert c.complete_structured(Autre, MSG, date_donnees=T).parsed.y == 2


def test_schema_sans_message_systeme_en_ajoute_un(fabrique):
    c = fabrique(responses=['{"x": 1}'])
    c.complete_structured(Reponse, [{"role": "user", "content": "q"}], date_donnees=T)
    premiers = c.mock.chat_calls[0]["messages"]
    assert premiers[0]["role"] == "system" and premiers[1]["content"] == "q"


# --------------------------------------------------------------------------- embeddings


def test_embed_passe_par_le_transport_et_le_cache(fabrique, cfg):
    c = fabrique(profile="prod")
    a = c.embed(["un", "deux"], date_donnees=T)
    b = c.embed(["un", "deux"], date_donnees=T)
    assert a.vectors == b.vectors and len(a.vectors) == 2
    embeds = [x for x in c.mock.calls if x["kind"] == "embed"]
    assert len(embeds) == 1 and embeds[0]["model"] == cfg.embeddings["prod"]
    assert b.record.cache_hit and a.record.prompt_id == "embed"


def test_embed_modele_selon_le_profil(fabrique, cfg):
    c = fabrique(profile="dev")
    c.embed(["a"], date_donnees=T)
    assert c.mock.calls[0]["model"] == cfg.embeddings["dev"]


def test_embed_journalise_les_quotas(fabrique, cfg):
    c = fabrique(profile="prod")
    c.embed(["a"], date_donnees=T)
    fournisseur = cfg.embeddings["prod"].split("/")[0]
    assert c.quotas.usage(fournisseur)["requests"] == 1


def test_embed_429_sans_relais(fabrique):
    c = fabrique()
    c.mock.fail("quota")
    with pytest.raises(QuotaEpuise):
        c.embed(["a"], date_donnees=T)


# --------------------------------------------------------------------------- agnosticisme


def test_changement_de_fournisseur_par_config_seule(tmp_path):
    """EX-NF-05 : même code, deux configurations ; seul l'identifiant de modèle change."""
    base = load_config()
    autre = load_config(
        overrides={
            "models": {
                "main": base.models["fallback"],
                "light": base.models["fallback"],
                "fallback": base.models["main"],
                "dev": base.models["dev"],
            }
        }
    )
    for config in (base, autre):
        c = MockLLMClient(
            config, profile="prod", cache_dir=tmp_path / "c", quota_journal=tmp_path / "q.json"
        )
        r = c.complete(MSG, date_donnees=T, tier="main", agent=config.models["main"])
        assert r.record.modele_demande == config.models["main"]
        assert c.mock.chat_calls[0]["model"] == config.models["main"]
    # Le fournisseur de tête a changé sans modifier une ligne de code.
    assert base.models["main"].split("/")[0] != autre.models["main"].split("/")[0]


def test_profil_dev_utilise_le_seul_modele_dev_sans_relais(fabrique, cfg):
    c = fabrique(profile="dev")
    r = c.complete(MSG, date_donnees=T, tier="main")
    assert c.mock.chat_calls[0]["model"] == cfg.models["dev"]
    assert r.record.tier == "dev" and r.record.fournisseur == cfg.models["dev"].split("/")[0]
    c.mock.fail("quota")
    with pytest.raises(QuotaEpuise):
        c.complete(MSG, date_donnees=date(2024, 2, 2))
    assert len(c.mock.chat_calls) == 2  # aucun relais vers un autre modèle


def test_profil_par_defaut_vient_de_la_config(tmp_path, cfg):
    c = MockLLMClient(cfg, cache_dir=tmp_path / "c", quota_journal=tmp_path / "q.json")
    assert c.profile == cfg.default_mode == "dev"


def test_un_fournisseur_non_declare_est_refuse_par_la_config():
    with pytest.raises(ValueError, match="fournisseur absent"):
        load_config(overrides={"models": {**load_config().models, "main": "inconnu/modele"}})


def test_le_vrai_client_ne_demande_pas_de_cle_pour_construire_le_mock(fabrique):
    assert isinstance(fabrique(), LLMClient)
    assert isinstance(fabrique().mock, MockTransport)


def test_mode_inconnu_refuse(tmp_path):
    with pytest.raises(ValueError):
        MockLLMClient(mode="turbo", cache_dir=tmp_path / "c", quota_journal=tmp_path / "q.json")
