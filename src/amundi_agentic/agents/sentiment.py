"""Agent Sentiment (allocation et titres) : résumé des news avec réflexion (outil de la tâche A).

Désactivé en backtest (D-044, EX-O1-17) : l'orchestrateur ne l'inclut parmi les votants qu'en live.
Le harnais lit les news via `as_of(t)`, appelle l'outil de résumé (niveau `light`, via `LLMClient`),
enregistre un `ToolCall` et expose le résumé et chaque article comme sources citables. Sans article
connu à t, l'agent s'abstient (couverture insuffisante signalée, jamais devinée).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from datetime import UTC, timedelta
from typing import Literal

from amundi_agentic.agents.base import LLMAgent
from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.evidence import Evidence, EvidenceSet
from amundi_agentic.agents.grounding import valeurs_ancrage
from amundi_agentic.data.models import NewsQuery
from amundi_agentic.schemas import Source, ToolCall, coupure
from amundi_agentic.tools.base import EXTRAIT_MAX


class SentimentAgent(LLMAgent):
    name = "sentiment"

    def __init__(self, level: Literal["allocation", "titre"]) -> None:
        self.level = level
        self.prompt_name = "sentiment_allocation" if level == "allocation" else "sentiment_titre"

    def _requete(self, ctx: AgentContext, actif: str | None) -> NewsQuery:
        cfg = ctx.settings.sentiment
        debut = ctx.t - timedelta(days=cfg.fenetre_jours)
        if actif is None:
            return NewsQuery(
                terms=tuple(cfg.termes_allocation), start=debut, limit=cfg.max_articles
            )
        return NewsQuery(tags=(actif,), start=debut, limit=cfg.max_articles)

    def collecter(self, ctx: AgentContext, assets: Sequence[str]) -> EvidenceSet:
        ev = EvidenceSet()
        cfg = ctx.settings.sentiment
        if ctx.summarizer is None:
            ev.manquants["resume_news"] = "outil de résumé non fourni"
            return ev
        cibles: list[tuple[str | None, str, str]]
        if self.level == "allocation":
            cibles = [(None, "marche", cfg.focus_allocation)]
        else:
            cibles = [(a, a, cfg.focus_titre) for a in assets]
        for actif, etiquette, focus in cibles:
            items = ctx.data.news(self._requete(ctx, actif))
            limite = coupure(ctx.t)
            items = [i for i in items if i.published_at < limite]  # ceinture point-in-time
            if not items:
                ev.manquants[f"news:{etiquette}"] = (
                    "aucune actualité connue à t sur la fenêtre : couverture insuffisante"
                )
                continue
            debut = time.perf_counter()
            res = ctx.summarizer(
                ctx.llm,
                items,
                ctx.t,
                focus=focus,
                reflection_rounds=cfg.reflexion_tours,
                tier="light",
            )
            ctx.n_appels_resume += int(getattr(res, "n_calls", 0))
            duree = int((time.perf_counter() - debut) * 1000)
            derniere = max(i.published_at for i in items).astimezone(UTC)
            sid = (
                "resume_news:"
                + etiquette
                + ":"
                + hashlib.sha256((res.summary + ctx.t.isoformat()).encode()).hexdigest()[:8]
            )
            src = Source(
                source_id=sid,
                type="sortie_outil",
                titre=f"Résumé des actualités ({etiquette})",
                reference=f"news_summary ; focus={focus} ; {len(items)} articles",
                date_publication=derniere,
                extrait=res.summary[:EXTRAIT_MAX] or "résumé vide",
            )
            appel = ToolCall(
                outil="news_summary",
                parametres={"actif": actif, "focus": focus, "n_articles": len(items)},
                resultat={
                    "summary": res.summary,
                    "key_points": list(res.key_points),
                    "n_calls": int(getattr(res, "n_calls", 0)),
                },
                duree_ms=duree,
                date_derniere_donnee=derniere.date(),
            )
            entete = f"[source_id={sid}] outil=news_summary" + (f" actif={actif}" if actif else "")
            corps = res.summary + "\n" + json.dumps(list(res.key_points), ensure_ascii=False)
            ev.items.append(
                Evidence(src, appel, entete + "\n" + corps, valeurs_ancrage(corps), actif, "texte")
            )
            for s in res.sources:
                if s.date_publication >= limite:
                    continue
                texte = f"[source_id={s.source_id}] news ({s.date_publication.date()}) : {s.titre} — {s.extrait}"
                ev.items.append(Evidence(s, None, texte, valeurs_ancrage(s.extrait), actif))
        return ev
