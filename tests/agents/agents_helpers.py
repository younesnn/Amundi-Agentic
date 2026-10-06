"""Fabriques communes des tests d'agents : contexte avec LLM simulé et données synthétiques."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.ports import FakeNewsSummaryTool, FakeRagTool
from amundi_agentic.agents.prompts import PromptLibrary
from amundi_agentic.agents.providers import SyntheticData
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.llm import MockLLMClient, load_config

T = date(2024, 2, 1)


def fabrique_ctx(
    tmp_path: Path,
    *,
    t: date = T,
    handler=politique_simulee,
    responses=(),
    profil="equilibre",
    stocks=("AAA", "BBB", "CCC"),
    esg_exclus=(),
    settings_overrides=None,
    avec_news: bool = True,
    cache: bool = True,
) -> AgentContext:
    cfg = load_config(overrides=None if cache else {"cache": {"enabled": False}})
    llm = MockLLMClient(
        cfg,
        mode="interactif",
        profile="dev",
        responses=list(responses),
        handler=handler,
        cache_dir=tmp_path / "cache",
        quota_journal=tmp_path / "quotas.json",
        run_dir=tmp_path / "run",
        run_id="test",
    )
    return AgentContext(
        t=t,
        profil=profil,
        run_id="test",
        llm=llm,
        data=SyntheticData(t, stocks=stocks, esg_exclus=esg_exclus, avec_news=avec_news),
        settings=load_settings(overrides=settings_overrides),
        prompts=PromptLibrary(),
        rag=FakeRagTool(),
        summarizer=FakeNewsSummaryTool(),
    )


@pytest.fixture
def ctx(tmp_path):
    return fabrique_ctx(tmp_path)
