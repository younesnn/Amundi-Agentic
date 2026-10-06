"""Contexte d'exécution partagé par les agents d'un run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from amundi_agentic.agents.evidence import EvidenceSet
from amundi_agentic.agents.ports import DataProvider, NewsSummaryTool, RagTool
from amundi_agentic.agents.prompts import PromptLibrary
from amundi_agentic.agents.settings import DebateSettings
from amundi_agentic.llm.client import LLMClient
from amundi_agentic.schemas import AppelJournal, ProfilRisque, VueRejetee


@dataclass
class AgentContext:
    t: date
    profil: ProfilRisque
    run_id: str
    llm: LLMClient
    data: DataProvider
    settings: DebateSettings
    prompts: PromptLibrary
    rag: RagTool | None = None
    summarizer: NewsSummaryTool | None = None
    # Un seul rapport de risque / ESG par date : les agents les consultent, ne les recalculent pas.
    cache: dict[Any, tuple[frozenset[str], EvidenceSet]] = field(default_factory=dict)
    appels: list[AppelJournal] = field(default_factory=list)
    rejets: list[VueRejetee] = field(default_factory=list)
    n_appels_resume: int = 0  # appels LLM faits par l'outil de résumé (budget)

    def vider_journaux(self) -> tuple[list[AppelJournal], list[VueRejetee]]:
        a, r = self.appels, self.rejets
        self.appels, self.rejets = [], []
        return a, r
