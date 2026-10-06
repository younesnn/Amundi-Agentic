"""Coordinateur : rapport consolidé (collaboration) et arbitrage des vues contestées (L1 §4, §6).

Il ne vote pas, ne produit aucune vue ni aucun chiffre, et ne décide pas du consensus (calculé en
Python dans `debate/consensus.py`). Rapport : trois blocs comme le papier (indicateurs positifs,
préoccupations, conclusion adaptée au profil). Si le LLM ne produit pas un rapport ancré après les
nouvelles demandes autorisées, un rapport de repli construit en Python (sans LLM) est utilisé et
signalé. Arbitrage : le LLM choisit un niveau dans [min, max] des votes ; le code le borne ensuite.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.evidence import neutraliser
from amundi_agentic.agents.grounding import valeurs_ancrage
from amundi_agentic.agents.risk import RiskResult
from amundi_agentic.agents.simple_call import appel_ancre
from amundi_agentic.llm.types import Message
from amundi_agentic.schemas import AgentTurn, EsgAssessment, View


class ReportDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    indicateurs_positifs: list[str] = Field(default_factory=list)
    preoccupations: list[str] = Field(default_factory=list)
    conclusion: str = ""


class ArbitrageItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    actif: str
    niveau: int
    justification: str


class ArbitrageDraft(BaseModel):
    """Un seul appel pour toutes les vues contestées d'un débat (budget : K <= 2, L1 §11.2)."""

    model_config = ConfigDict(extra="ignore")
    arbitrages: list[ArbitrageItem]


@dataclass
class Rapport:
    texte: str
    repli: bool  # True : rapport construit en Python, pas par le LLM
    motif_repli: str | None = None


@dataclass
class Arbitrage:
    niveau_choisi: int  # avant bornage
    justification: str
    repli: bool


def _vues_texte(turns: Sequence[AgentTurn]) -> tuple[str, list[str]]:
    lignes: list[str] = []
    textes: list[str] = []
    for t in turns:
        for v in t.vues:
            lignes.append(f"- {t.agent} / {v.actif} : {v.direction.value}")
            for a in v.arguments_pour:
                lignes.append(f"    pour : {neutraliser(a)}")
                textes.append(a)
            for a in v.arguments_contre:
                lignes.append(f"    contre : {neutraliser(a)}")
                textes.append(a)
            textes.extend(s.extrait for s in v.sources)
    return "\n".join(lignes), textes


def _rendre(d: ReportDraft) -> str:
    pos = "\n".join(f"- {x}" for x in d.indicateurs_positifs) or "- (aucun)"
    pre = "\n".join(f"- {x}" for x in d.preoccupations) or "- (aucune)"
    return f"## Indicateurs positifs\n{pos}\n\n## Préoccupations\n{pre}\n\n## Conclusion\n{d.conclusion}"


class Coordinator:
    name = "coordinateur"

    def rapport(
        self,
        ctx: AgentContext,
        turns: Sequence[AgentTurn],
        risque: RiskResult | None,
        vetoes: Sequence[EsgAssessment] = (),
    ) -> Rapport:
        decrit, textes = _vues_texte(turns)
        donnees_risque = (
            {
                "alertes": risque.assessment.alertes,
                "regime_volatilite": risque.assessment.regime_volatilite,
            }
            if risque
            else {}
        )
        valeurs = valeurs_ancrage([textes, donnees_risque])
        composite = ctx.prompts.compose("coordinator_report", variables={})
        user = (
            f"Date : {ctx.t.isoformat()}. Profil du client : {ctx.profil}.\n"
            f"Analyses des agents :\n<<<DONNEES\n{decrit}\nDONNEES>>>\n"
            f"Alertes de risque calculées : {json.dumps(donnees_risque, ensure_ascii=False)}\n"
            f"Actifs sous veto ESG (exclus du débat) : {[v.actif for v in vetoes]}"
        )
        parsed, motif = appel_ancre(
            ctx,
            agent=self.name,
            tour=0,
            nature="rapport",
            composite=composite,
            messages=[
                Message(role="system", content=composite.texte),
                Message(role="user", content=user),
            ],
            schema=ReportDraft,
            textes=lambda p: [*p.indicateurs_positifs, *p.preoccupations, p.conclusion],
            valeurs=valeurs,
            verifier=lambda p: None if p.conclusion.strip() else "conclusion vide",
        )
        if parsed is not None:
            return Rapport(_rendre(parsed), False)
        return Rapport(self._repli(ctx, turns, vetoes), True, motif)

    @staticmethod
    def _repli(
        ctx: AgentContext, turns: Sequence[AgentTurn], vetoes: Sequence[EsgAssessment]
    ) -> str:
        pos: list[str] = []
        pre: list[str] = []
        for t in turns:
            for v in t.vues:
                if v.direction.n > 0:
                    pos.append(f"{t.agent} / {v.actif} : {v.arguments_pour[0]}")
                pre.append(f"{t.agent} / {v.actif} : {v.arguments_contre[0]}")
        d = ReportDraft(
            indicateurs_positifs=pos,
            preoccupations=pre,
            conclusion=(
                "Rapport de repli construit en Python (le rapport du LLM n'a pas passé le contrôle "
                f"d'ancrage). Profil du client : {ctx.profil}. Actifs sous veto : "
                f"{[v.actif for v in vetoes] or 'aucun'}."
            ),
        )
        return _rendre(d)

    def arbitrer_lot(
        self,
        ctx: AgentContext,
        contestes: dict[str, Sequence[View]],
        *,
        tour: int,
    ) -> dict[str, Arbitrage]:
        """Arbitre toutes les vues contestées d'un débat en UN appel. Un actif dont l'arbitrage est
        absent, hors de [min, max] des votes ou non ancré reçoit un arbitrage de repli
        (médiane des votes arrondie vers 0), signalé par `repli=True`."""
        if not contestes:
            return {}
        bornes = {
            a: (min(v.direction.n for v in vs), max(v.direction.n for v in vs))
            for a, vs in contestes.items()
        }
        blocs: list[str] = []
        textes_ancrage: list[list[str]] = []
        for a, vs in contestes.items():
            lo, hi = bornes[a]
            blocs.append(f"### actif={a} min={lo} max={hi}")
            for v in vs:
                blocs.append(
                    f"- {v.auteur} : {v.direction.value} ; "
                    f"pour : {[neutraliser(x) for x in v.arguments_pour]} ; "
                    f"contre : {[neutraliser(x) for x in v.arguments_contre]}"
                )
                textes_ancrage.append(
                    [*v.arguments_pour, *v.arguments_contre, *(s.extrait for s in v.sources)]
                )
        composite = ctx.prompts.compose("coordinator_arbitrage", variables={})
        user = (
            f"Profil du client : {ctx.profil}. Vues contestées à arbitrer, une entrée par actif :\n"
            "<<<DONNEES\n" + "\n".join(blocs) + "\nDONNEES>>>"
        )

        def verifier(p: ArbitrageDraft) -> str | None:
            vus = [i.actif for i in p.arbitrages]
            if sorted(vus) != sorted(contestes):
                return f"un arbitrage exactement par actif contesté {sorted(contestes)}"
            for i in p.arbitrages:
                lo, hi = bornes[i.actif]
                if not lo <= i.niveau <= hi:
                    return f"niveau {i.niveau} de {i.actif} hors de [{lo}, {hi}]"
            return None

        parsed, motif = appel_ancre(
            ctx,
            agent=self.name,
            tour=tour,
            nature="arbitrage",
            composite=composite,
            messages=[
                Message(role="system", content=composite.texte),
                Message(role="user", content=user),
            ],
            schema=ArbitrageDraft,
            textes=lambda p: [i.justification for i in p.arbitrages],
            valeurs=valeurs_ancrage(textes_ancrage),
            verifier=verifier,
        )
        sortie: dict[str, Arbitrage] = {}
        for a, vs in contestes.items():
            choisi = next((i for i in parsed.arbitrages if i.actif == a), None) if parsed else None
            if choisi is not None:
                sortie[a] = Arbitrage(choisi.niveau, choisi.justification, False)
                continue
            tries = sorted(v.direction.n for v in vs)
            n = len(tries)
            med = tries[n // 2] if n % 2 else int((tries[n // 2 - 1] + tries[n // 2]) / 2)
            sortie[a] = Arbitrage(
                med,
                f"Arbitrage de repli : médiane des votes (réponse du LLM non retenue : {motif}).",
                True,
            )
        return sortie
