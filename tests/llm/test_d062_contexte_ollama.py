"""D-062 : `num_ctx` transmis à Ollama, détection de la troncature silencieuse du prompt, clé de
cache et journal. Transport simulé : aucune clé ni réseau."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from amundi_agentic.llm import (
    LLMError,
    MockTransport,
    PromptTronque,
    ProviderError,
    load_config,
)
from amundi_agentic.llm.__main__ import main as cli_llm
from amundi_agentic.llm.cache import DiskCache, cache_key
from amundi_agentic.llm.transport import LiteLLMTransport
from amundi_agentic.llm.types import RawCompletion

T = date(2024, 2, 1)
LONG = "mot " * 9000  # 36 000 caractères : environ 8 000 jetons estimés (ratio 4,5)


def _brut(tokens_in, texte="ok", servi="llama3.1:8b"):
    return RawCompletion(texte, servi, tokens_in, 5)


def _fichiers_cache(client):
    return list(client.cache.directory.glob("??/*.json"))


@pytest.fixture
def cfg_ollama_principal(cfg):
    """Chaîne interactive `main` = Ollama puis Groq : permet de prouver l'absence de relais."""
    return load_config(overrides={"models": {**cfg.models, "main": cfg.models["dev"]}})


def test_config_fixe_num_ctx_et_detection(cfg):
    assert cfg.ollama.num_ctx == 16384
    assert "ollama" in cfg.truncation_check.providers
    assert cfg.truncation_check.chars_per_token == 4.5
    assert cfg.truncation_check.min_estimated_tokens == 1000
    assert cfg.truncation_check.min_ratio == 0.5
    assert cfg.provider_params("ollama") == {"num_ctx": 16384}
    assert cfg.provider_params("gemini") == {}


# ------------------------------------------------------------------ troncature


def test_troncature_leve_prompt_tronque(fabrique, tmp_path):
    c = fabrique(profile="dev", run_dir=tmp_path / "run")
    c.mock.push(_brut(2050))
    with pytest.raises(PromptTronque) as e:
        c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    assert isinstance(e.value, LLMError) and not isinstance(e.value, ProviderError)
    assert (e.value.estimes, e.value.evalues, e.value.num_ctx) == (8000, 2050, 16384)
    msg = str(e.value)
    assert "8000" in msg and "2050" in msg and "16384" in msg


def test_troncature_sans_cache_ni_nouvelle_tentative(fabrique):
    c = fabrique(profile="dev")
    c.mock.push(_brut(2050), _brut(2050))
    for _ in range(2):
        with pytest.raises(PromptTronque):
            c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    assert len(c.mock.chat_calls) == 2  # un appel par complete : pas de nouvelle tentative
    assert _fichiers_cache(c) == []  # rien n'a été mis en cache


def test_troncature_sans_relais(fabrique, cfg_ollama_principal):
    c = fabrique(config=cfg_ollama_principal, profile="prod")
    c.mock.push(_brut(2050))
    with pytest.raises(PromptTronque):
        c.complete([{"role": "user", "content": LONG}], date_donnees=T, tier="main")
    modeles = {a["model"] for a in c.mock.chat_calls}
    assert modeles == {cfg_ollama_principal.models["dev"]}  # jamais le modèle de relais
    assert c.usage()["appels"] == 0


def test_troncature_sortie_structuree_pas_de_retentative(fabrique):
    from pydantic import BaseModel

    class S(BaseModel):
        a: int

    c = fabrique(profile="dev")
    c.mock.push(_brut(2050, '{"a": 1}'))
    with pytest.raises(PromptTronque):
        c.complete_structured(S, [{"role": "user", "content": LONG}], date_donnees=T)
    assert len(c.mock.chat_calls) == 1 and _fichiers_cache(c) == []


def test_troncature_enregistree_dans_le_journal(fabrique, tmp_path):
    c = fabrique(profile="dev", run_dir=tmp_path / "run")
    c.mock.push(_brut(2050))
    with pytest.raises(PromptTronque):
        c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    rec = c.records[-1]
    assert rec.erreur and rec.erreur.startswith("prompt_tronque")
    assert (rec.prompt_tokens_evalues, rec.prompt_tokens_estimes, rec.num_ctx) == (
        2050,
        8000,
        16384,
    )
    ligne = json.loads((tmp_path / "run" / "calls.jsonl").read_text().splitlines()[-1])
    assert ligne["prompt_tokens_evalues"] == 2050 and ligne["num_ctx"] == 16384
    assert ligne["erreur"].startswith("prompt_tronque")


def test_troncature_aussi_en_mode_evaluation_impossible_avec_dev(fabrique):
    """Le profil dev est interdit en évaluation : la détection d'un fournisseur de la liste
    s'applique donc en interactif ; en évaluation, elle s'appliquerait de même à un modèle
    Ollama figé (contrôle indépendant du mode)."""
    cfg = load_config(overrides={"truncation_check": {"providers": ["gemini", "ollama"]}})
    c = fabrique(config=cfg, mode="evaluation", profile="prod")
    c.mock.push(_brut(2050, servi="gemini-3.8-flash"))
    with pytest.raises(PromptTronque):
        c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    assert _fichiers_cache(c) == []


def test_prompt_court_aucune_detection(fabrique):
    c = fabrique(profile="dev")
    c.mock.push(_brut(3))  # 3 jetons évalués pour un prompt court : normal
    r = c.complete([{"role": "user", "content": "bonjour " * 100}], date_donnees=T)
    assert r.text == "ok"
    assert r.record.prompt_tokens_evalues == 3


def test_sous_le_seuil_pas_de_faux_positif(fabrique):
    c = fabrique(profile="dev")
    # 4 400 caractères = 977 jetons estimés < 1 000 : jamais contrôlé, même avec 1 jeton évalué
    c.mock.push(_brut(1))
    r = c.complete([{"role": "user", "content": "a" * 4400}], date_donnees=T)
    assert r.text == "ok"


def test_prompt_long_correctement_evalue_passe_et_est_enregistre(fabrique, tmp_path):
    c = fabrique(profile="dev", run_dir=tmp_path / "run")
    c.mock.push(_brut(11000))
    r = c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    assert r.record.prompt_tokens_evalues == 11000
    assert r.record.prompt_tokens_estimes == 8000 and r.record.num_ctx == 16384
    ligne = json.loads((tmp_path / "run" / "calls.jsonl").read_text().splitlines()[-1])
    assert ligne["num_ctx"] == 16384 and ligne["prompt_tokens_evalues"] == 11000
    assert len(_fichiers_cache(c)) == 1
    # le journal d'un cache hit n'invente pas de jetons évalués
    r2 = c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    assert r2.record.cache_hit and r2.record.prompt_tokens_evalues is None


def test_limite_exacte_du_ratio(fabrique):
    c = fabrique(profile="dev")
    c.mock.push(_brut(4000), _brut(3999))  # 0,5 x 8000 = 4000 : accepté ; 3999 : refusé
    c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    with pytest.raises(PromptTronque):
        c.complete([{"role": "user", "content": LONG + "x"}], date_donnees=T)


def test_fournisseur_hors_liste_non_controle(fabrique):
    c = fabrique(profile="prod")  # Gemini : hors de truncation_check.providers
    c.mock.push(_brut(10, servi="gemini-flash"))
    assert c.complete([{"role": "user", "content": LONG}], date_donnees=T).text == "ok"


# ------------------------------------------------------------------ num_ctx transmis


def test_num_ctx_transmis_au_transport(fabrique):
    c = fabrique(profile="dev")
    c.mock.push(_brut(11000))
    c.complete([{"role": "user", "content": LONG}], date_donnees=T)
    assert c.mock.chat_calls[0]["extra_params"] == {"num_ctx": 16384}


def test_num_ctx_suit_la_configuration(fabrique, cfg):
    cfg2 = load_config(overrides={"ollama": {"num_ctx": 8192}})
    c = fabrique(config=cfg2, profile="dev")
    c.complete([{"role": "user", "content": "salut"}], date_donnees=T)
    assert c.mock.chat_calls[0]["extra_params"] == {"num_ctx": 8192}


def test_pas_de_num_ctx_pour_gemini(fabrique):
    c = fabrique(profile="prod")
    c.complete([{"role": "user", "content": "salut"}], date_donnees=T)
    assert c.mock.chat_calls[0]["extra_params"] == {}


def test_transport_litellm_passe_num_ctx(monkeypatch):
    monkeypatch.setattr("amundi_agentic.llm.transport.load_dotenv", lambda *a, **k: None)
    t = LiteLLMTransport(load_config())
    appels = []

    class Lib:
        def completion(self, **kw):
            appels.append(kw)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                model="m",
                usage=SimpleNamespace(prompt_tokens=7, completion_tokens=1),
            )

    t._litellm = Lib()
    kw = dict(
        model="ollama/x",
        messages=[{"role": "user", "content": "a"}],
        temperature=0,
        seed=0,
        max_tokens=None,
        timeout=5,
        json_mode=False,
    )
    t.completion(**kw, extra_params={"num_ctx": 16384})
    t.completion(**kw)
    assert appels[0]["num_ctx"] == 16384 and "num_ctx" not in appels[1]


# ------------------------------------------------------------------ cache


def _cle(**params):
    return cache_key(
        kind="chat",
        model="ollama/x",
        messages=[{"role": "user", "content": "a"}],
        schema=None,
        params={"temperature": 0, "seed": 0, "max_tokens": None, **params},
        date_donnees=T,
        scope="interactif/dev",
    )


def test_cle_de_cache_depend_de_num_ctx():
    assert _cle(num_ctx=2048) != _cle(num_ctx=16384)
    assert _cle() != _cle(num_ctx=16384)


def test_cle_de_cache_client_depend_de_num_ctx(fabrique):
    cles = set()
    for n in (4096, 16384):
        c = fabrique(config=load_config(overrides={"ollama": {"num_ctx": n}}), profile="dev")
        cles.add(
            c.complete([{"role": "user", "content": "salut"}], date_donnees=T).record.cle_cache
        )
    assert len(cles) == 2


def test_resultat_ancien_contexte_jamais_reutilise(fabrique, tmp_path):
    cache = tmp_path / "cache"
    a = fabrique(
        config=load_config(overrides={"ollama": {"num_ctx": 2048}}), profile="dev", cache=cache
    )
    a.complete([{"role": "user", "content": "salut"}], date_donnees=T)
    b = fabrique(profile="dev", cache=cache)
    r = b.complete([{"role": "user", "content": "salut"}], date_donnees=T)
    assert not r.record.cache_hit and len(b.mock.chat_calls) == 1


def test_schema_de_cle_versionne_invalide_les_anciens_caches(tmp_path):
    """Une entrée écrite sous l'ancien schéma de clé (sans version) n'est plus atteignable."""
    import hashlib

    ancien = {
        "kind": "chat",
        "model": "ollama/x",
        "messages": [{"role": "user", "content": "a"}],
        "schema": None,
        "params": {"temperature": 0, "seed": 0, "max_tokens": None},
        "date_donnees": T.isoformat(),
        "scope": "interactif/dev",
    }
    brut = json.dumps(ancien, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    cle_ancienne = hashlib.sha256(brut.encode()).hexdigest()
    assert cle_ancienne != _cle()


def test_purge_cache_par_fournisseur(tmp_path, capsys):
    cache = DiskCache(tmp_path / "cache")
    cache.put("aa" + "0" * 62, {"text": "x", "modele_servi": "m", "fournisseur": "ollama"})
    cache.put("ab" + "1" * 62, {"text": "y", "modele_servi": "m", "fournisseur": "gemini"})
    cache.put("ac" + "2" * 62, {"text": "z", "modele_servi": "m", "fournisseur": "ollama"})
    assert cache.purge("ollama") == 2
    restant = list((tmp_path / "cache").glob("??/*.json"))
    assert [json.loads(p.read_text())["fournisseur"] for p in restant] == ["gemini"]
    assert cli_llm(["purge-cache", "gemini", "--dir", str(tmp_path / "cache")]) == 0
    assert "1 entrée" in capsys.readouterr().out
    assert list((tmp_path / "cache").glob("??/*.json")) == []


def test_purge_cache_dossier_absent(tmp_path):
    assert DiskCache(tmp_path / "rien").purge("ollama") == 0


def test_mock_transport_signature_compatible():
    t = MockTransport(default_text="ok")
    r = t.completion(
        model="m",
        messages=[{"role": "user", "content": "a"}],
        temperature=0,
        seed=0,
        max_tokens=None,
        timeout=1,
        json_mode=False,
    )
    assert r.text == "ok"
