"""Agents spécialisés (phase 3) : macro, valuation, risque, fundamental, sentiment, ESG, coordinateur.

Conception « outils d'abord » : le harnais exécute les outils (`tools/`), enregistre un `ToolCall` par
appel, puis le LLM commente et produit une `View` structurée ; chiffres et sources sont contrôlés
(`grounding.py`). Aucun prompt n'est écrit dans le code (`agent_prompts/`, `prompts.py`).
"""

from amundi_agentic.agents.base import AgentResult, LLMAgent
from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.fundamental import FundamentalAgent
from amundi_agentic.agents.macro import MacroAgent
from amundi_agentic.agents.prompts import PromptLibrary, load_prompt
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.agents.sentiment import SentimentAgent
from amundi_agentic.agents.settings import DebateSettings, load_settings
from amundi_agentic.agents.valuation import ValuationAgent

__all__ = [
    "AgentContext",
    "AgentResult",
    "Coordinator",
    "DebateSettings",
    "EsgAgent",
    "FundamentalAgent",
    "LLMAgent",
    "MacroAgent",
    "PromptLibrary",
    "RiskAgent",
    "SentimentAgent",
    "ValuationAgent",
    "load_prompt",
    "load_settings",
]
