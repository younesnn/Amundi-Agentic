"""Transport LiteLLM, testé sans réseau avec une fausse bibliothèque injectée : classement des
erreurs, lecture du modèle servi, gestion des clés (jamais affichées)."""

from types import SimpleNamespace

import pytest

from amundi_agentic.llm import ConfigurationError, ProviderError, load_config
from amundi_agentic.llm.transport import LiteLLMTransport

CLE = "AIza" + "Sy" + "z" * 33


class RateLimitError(Exception):  # même nom que la classe de LiteLLM : classement par nom
    status_code = 429


class ServiceUnavailableError(Exception):
    status_code = 503


class Timeout(Exception):  # noqa: N818
    pass


class AuthenticationError(Exception):
    status_code = 401


class FausseLib:
    def __init__(self, erreur=None):
        self.erreur = erreur
        self.appels = []

    def completion(self, **kw):
        self.appels.append(kw)
        if self.erreur:
            raise self.erreur
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="bonjour"))],
            model="version-servie",
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3),
        )

    def embedding(self, **kw):
        self.appels.append(kw)
        if self.erreur:
            raise self.erreur
        return SimpleNamespace(
            data=[{"index": 1, "embedding": [0.3]}, {"index": 0, "embedding": [0.1, 0.2]}],
            model="emb-servi",
            usage=SimpleNamespace(prompt_tokens=4),
        )


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr("amundi_agentic.llm.transport.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", CLE)
    cfg = load_config()
    t = LiteLLMTransport(cfg)
    t._litellm = FausseLib()
    return t, cfg


def appel(t, model, **kw):
    return t.completion(
        model=model,
        messages=[{"role": "user", "content": "x"}],
        temperature=0,
        seed=3,
        max_tokens=None,
        timeout=5,
        json_mode=kw.pop("json_mode", False),
    )


def test_completion_lit_modele_servi_et_jetons(transport):
    t, cfg = transport
    r = appel(t, cfg.models["main"], json_mode=True)
    assert (r.text, r.model_served, r.tokens_in, r.tokens_out) == (
        "bonjour",
        "version-servie",
        11,
        3,
    )
    kw = t._litellm.appels[0]
    assert kw["num_retries"] == 0 and kw["temperature"] == 0 and kw["seed"] == 3
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["api_key"] == CLE  # transmise en mémoire à la bibliothèque, jamais écrite ailleurs


def test_cle_absente_message_sans_valeur(monkeypatch):
    monkeypatch.setattr("amundi_agentic.llm.transport.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = load_config()
    t = LiteLLMTransport(cfg)
    t._litellm = FausseLib()
    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        appel(t, cfg.models["fallback"])


def test_ollama_sans_cle_et_avec_base_locale(monkeypatch, transport):
    t, cfg = transport
    monkeypatch.setenv("OLLAMA_API_BASE", "http://localhost:11434")
    appel(t, cfg.models["dev"])
    kw = t._litellm.appels[0]
    assert "api_key" not in kw and kw["api_base"] == "http://localhost:11434"


@pytest.mark.parametrize(
    ("erreur", "kind"),
    [
        (RateLimitError("trop de requêtes"), "quota"),
        (ServiceUnavailableError("indisponible"), "unavailable"),
        (Timeout("délai dépassé"), "timeout"),
        (AuthenticationError("refusé"), "auth"),
        (ValueError("autre"), "other"),
    ],
)
def test_erreurs_classees(transport, erreur, kind):
    t, cfg = transport
    t._litellm = FausseLib(erreur)
    with pytest.raises(ProviderError) as e:
        appel(t, cfg.models["main"])
    assert e.value.kind == kind


def test_erreur_du_fournisseur_masque_la_cle(transport):
    t, cfg = transport
    t._litellm = FausseLib(RateLimitError(f"429 pour https://x.invalid/v1?key={CLE}"))
    with pytest.raises(ProviderError) as e:
        appel(t, cfg.models["main"])
    assert CLE not in str(e.value)


def test_embedding_reordonne_les_vecteurs(transport):
    t, cfg = transport
    r = t.embedding(model=cfg.embeddings["prod"], inputs=["a", "b"], timeout=5)
    assert r.vectors == [[0.1, 0.2], [0.3]] and r.model_served == "emb-servi" and r.tokens_in == 4


def test_embed_passe_par_litellm(transport, tmp_path):
    """EX-NF-14 : LLMClient.embed appelle bien `litellm.embedding` via le transport réel."""
    from datetime import date

    from amundi_agentic.llm import LLMClient

    t, cfg = transport
    c = LLMClient(
        cfg,
        profile="prod",
        transport=t,
        cache_dir=tmp_path / "c",
        quota_journal=tmp_path / "q.json",
    )
    r = c.embed(["a", "b"], date_donnees=date(2024, 2, 1))
    assert len(r.vectors) == 2
    assert t._litellm.appels[0]["model"] == cfg.embeddings["prod"]
    assert t._litellm.appels[0]["input"] == ["a", "b"]
