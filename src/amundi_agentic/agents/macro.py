"""Agent Macro (allocation) : régime croissance x inflation, taux, courbe, crédit, VIX.

Outil : `tools/macro_regime.py` (calcul Python). Le LLM relie le régime aux classes, sans chiffre propre.
"""

from __future__ import annotations

from collections.abc import Sequence

from amundi_agentic.agents.base import LLMAgent
from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.evidence import EvidenceSet, executer_outil
from amundi_agentic.tools import macro_regime as mr


class MacroAgent(LLMAgent):
    name = "macro"
    level = "allocation"
    prompt_name = "macro"

    def collecter(self, ctx: AgentContext, assets: Sequence[str]) -> EvidenceSet:
        ev = EvidenceSet()
        series, absentes = ctx.data.macro_series(list(mr.DEFAULT_IDS.values()))
        for sid, raison in absentes.items():
            ev.manquants[sid] = raison
        executer_outil(
            ev,
            ctx.t,
            lambda: mr.macro_regime(series, ctx.t),
            cle="macro_regime",
            libelle="Régime macroéconomique (FRED, BCE)",
        )
        return ev
