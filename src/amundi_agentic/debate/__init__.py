"""Orchestration du débat round robin, consensus et journaux (phase 3)."""

from amundi_agentic.debate.consensus import accord, confiance, evaluer, mediane_vers_zero
from amundi_agentic.debate.devil import designer
from amundi_agentic.debate.orchestrator import DebateResult, construire_votants, run_debate

__all__ = [
    "DebateResult",
    "accord",
    "confiance",
    "construire_votants",
    "designer",
    "evaluer",
    "mediane_vers_zero",
    "run_debate",
]
