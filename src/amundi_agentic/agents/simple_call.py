"""Appel LLM structuré avec contrôle d'ancrage des chiffres, pour les sorties qui ne sont pas des vues
(commentaire de l'agent Risque, rapport et arbitrage du coordinateur, explication d'un veto)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal, TypeVar

from pydantic import BaseModel

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.grounding import chiffres_non_ancres
from amundi_agentic.agents.prompts import PromptComposite
from amundi_agentic.llm.types import LLMError, Message, StructuredOutputError
from amundi_agentic.schemas import AppelJournal

T = TypeVar("T", bound=BaseModel)
Nature = Literal["rapport", "arbitrage", "commentaire", "explication"]


def appel_ancre(
    ctx: AgentContext,
    *,
    agent: str,
    tour: int,
    nature: Nature,
    composite: PromptComposite,
    messages: list[Message],
    schema: type[T],
    textes: Callable[[T], Sequence[str]],
    valeurs: Sequence[float],
    verifier: Callable[[T], str | None] = lambda _p: None,
) -> tuple[T | None, str | None]:
    """Renvoie (objet validé, None) ou (None, motif de rejet). Au plus `max_retries` redemandes."""
    cfg = ctx.settings.grounding
    motif = "aucune réponse"
    for _ in range(cfg.max_retries + 1):
        try:
            res = ctx.llm.complete_structured(
                schema,
                messages,
                date_donnees=ctx.t,
                tier=composite.niveau,
                agent=agent,
                prompt_ref=composite.ref,
            )
        except StructuredOutputError as exc:
            return (
                None,
                f"sortie non conforme au schéma : {str(exc)[: ctx.settings.limites.motif_max_caracteres]}",
            )
        except LLMError:
            raise
        ctx.appels.append(
            AppelJournal(
                agent=agent,
                tour=tour,
                nature=nature,
                prompt_id=composite.ref.prompt_id,
                prompt_version=composite.ref.version,
                prompt_sha256=composite.ref.sha256,
                messages=[m.model_dump() for m in messages],
                reponse=res.text,
                record=res.record,
            )
        )
        parsed = res.parsed
        assert isinstance(parsed, schema)
        faute = verifier(parsed)
        if faute is None:
            manquants = chiffres_non_ancres(textes(parsed), list(valeurs), cfg)
            faute = (
                f"chiffres introuvables dans les sorties d'outils : {manquants}"
                if manquants
                else None
            )
        if faute is None:
            return parsed, None
        motif = faute
        messages = [
            *messages,
            Message(role="assistant", content=res.text),
            Message(
                role="user",
                content=(
                    f"Ta réponse est refusée par le contrôle d'ancrage : {faute}. "
                    "Corrige et renvoie uniquement l'objet JSON complet."
                ),
            ),
        ]
    return None, motif
