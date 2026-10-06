"""Agent Valuation / Momentum : allocation (une série par classe) et titres (une série par titre).

Outil : `tools/momentum.py` `valuation_summary` (rendement annualisé et volatilité du papier,
momentum 12-1, perte maximale, écart à la moyenne mobile 200 jours...). Le LLM commente.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from amundi_agentic.agents.base import LLMAgent
from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.evidence import EvidenceSet, executer_outil
from amundi_agentic.tools import momentum


class ValuationAgent(LLMAgent):
    name = "valuation"

    def __init__(self, level: Literal["allocation", "titre"]) -> None:
        self.level = level
        self.prompt_name = "valuation_allocation" if level == "allocation" else "valuation_titre"

    def collecter(self, ctx: AgentContext, assets: Sequence[str]) -> EvidenceSet:
        ev = EvidenceSet()
        rf = ctx.data.risk_free_annual()
        taux = rf.value if rf is not None else 0.0
        if rf is None:
            ev.manquants["taux_sans_risque"] = (
                "indisponible : Sharpe et Sortino calculés avec un taux sans risque nul"
            )
        fenetre = ctx.settings.valuation.fenetre_seances
        for a in assets:
            prix = (
                ctx.data.class_prices(a) if self.level == "allocation" else ctx.data.stock_prices(a)
            )
            executer_outil(
                ev,
                ctx.t,
                lambda p=prix: momentum.valuation_summary(p, ctx.t, taux, fenetre),
                cle=f"valuation_summary:{a}",
                actif=a,
                libelle=f"Valuation et momentum : {a}",
                params={"rf_annual": taux},
            )
        return ev
