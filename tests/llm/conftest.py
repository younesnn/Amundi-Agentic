"""Fixtures communes : client sur transport simulé, aucune clé ni réseau (EX-NF-12)."""

import pytest

from amundi_agentic.llm import MockLLMClient, load_config


@pytest.fixture(autouse=True)
def _sans_cle(monkeypatch):
    """Aucun secret réel ne doit exister pendant ces tests."""
    for nom in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(nom, raising=False)


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def fabrique(tmp_path, cfg):
    """Fabrique de clients simulés partageant (par défaut) le même cache."""

    def make(*, config=None, mode="interactif", profile="prod", cache=None, **kw):
        return MockLLMClient(
            config or cfg,
            mode=mode,
            profile=profile,
            cache_dir=cache or tmp_path / "cache",
            quota_journal=tmp_path / "quotas.json",
            **kw,
        )

    return make
