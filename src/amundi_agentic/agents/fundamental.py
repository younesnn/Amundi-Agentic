"""Agent Fundamental (titres) : RAG sur les 10-K et 10-Q (outil de la tâche A) et faits XBRL.

Le harnais indexe les dépôts connus à t, pose les questions du papier (configurées dans
`config/debate.yaml`), enregistre un `ToolCall` par question et injecte les passages avec leurs
sources (`depot_sec`). Les faits XBRL sont lus en Python (dernier dépôt `filed` < t par période) :
aucun appel d'API généré par le LLM. Un passage dont la source est datée à t ou après est écarté.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC

import pandas as pd

from amundi_agentic.agents.base import LLMAgent
from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.evidence import Evidence, EvidenceSet, jsonable
from amundi_agentic.agents.grounding import valeurs_ancrage
from amundi_agentic.schemas import Source, ToolCall, coupure
from amundi_agentic.tools.base import EXTRAIT_MAX


class FundamentalAgent(LLMAgent):
    name = "fundamental"
    level = "titre"
    prompt_name = "fundamental"

    def collecter(self, ctx: AgentContext, assets: Sequence[str]) -> EvidenceSet:
        ev = EvidenceSet()
        cfg = ctx.settings.fundamental
        limite = coupure(ctx.t)
        for ticker in assets:
            self._xbrl(ctx, ev, ticker)
            if ctx.rag is None:
                ev.manquants[f"rag:{ticker}"] = "outil RAG non fourni"
                continue
            try:
                n_index = ctx.rag.index_filings(ticker, ctx.t)
            except (KeyError, ValueError) as e:
                ev.manquants[f"rag:{ticker}"] = f"indexation impossible : {e}"
                continue
            for question in cfg.questions:
                debut = time.perf_counter()
                res = ctx.rag.query(ticker, question, ctx.t, k=cfg.rag_k)
                duree = int((time.perf_counter() - debut) * 1000)
                passages = [p for p in res.passages if p.source.date_publication < limite]
                appel = ToolCall(
                    outil="rag_query",
                    parametres={
                        "actif": ticker,
                        "question": question,
                        "k": cfg.rag_k,
                        "indexes": n_index,
                    },
                    resultat={
                        "passages": [
                            {
                                "source_id": p.source.source_id,
                                "section": p.section,
                                "score": jsonable(p.score),
                            }
                            for p in passages
                        ]
                    },
                    duree_ms=duree,
                    date_derniere_donnee=max(
                        (p.source.date_publication.date() for p in passages), default=None
                    ),
                )
                if not passages:
                    ev.manquants[f"rag:{ticker}:{question[:40]}"] = (
                        "aucun passage retrouvé : sans réponse"
                    )
                    ev.items.append(
                        Evidence(
                            None,
                            appel,
                            f"Question sans passage retrouvé pour {ticker} : {question}",
                            [],
                            ticker,
                        )
                    )
                    continue
                dejas = {e.source_id for e in ev.items if e.source_id}
                appel_porte = False
                for p in passages:
                    if p.source.source_id in dejas:
                        continue  # même passage retrouvé par une autre question : une seule fois
                    dejas.add(p.source.source_id)
                    texte = (
                        f"[source_id={p.source.source_id}] actif={ticker} outil=rag section={p.section} "
                        f"question=« {question} »\n{p.text[: cfg.max_caracteres_passage]}"
                    )
                    ev.items.append(
                        Evidence(
                            p.source,
                            None if appel_porte else appel,
                            texte,
                            valeurs_ancrage(p.text),
                            ticker,
                            "texte",
                        )
                    )
                    appel_porte = True
                if not appel_porte:  # tous les passages déjà présents : la trace de l'appel reste
                    ev.items.append(
                        Evidence(None, appel, f"Question déjà couverte : {question}", [], ticker)
                    )
        return ev

    def _xbrl(self, ctx: AgentContext, ev: EvidenceSet, ticker: str) -> None:
        cfg = ctx.settings.fundamental
        if cfg.concepts_xbrl_max <= 0:
            return
        debut = time.perf_counter()
        df = ctx.data.xbrl_facts(ticker)
        if df is None or df.empty:
            ev.manquants[f"xbrl:{ticker}"] = "aucun fait XBRL connu à t"
            return
        df = df[df["filed"] < pd.Timestamp(ctx.t)]
        if df.empty:
            ev.manquants[f"xbrl:{ticker}"] = "aucun fait XBRL déposé avant t"
            return
        dernier = df.sort_values(["concept", "end", "filed"]).groupby("concept").tail(1)
        dernier = dernier.head(cfg.concepts_xbrl_max)
        faits = {
            str(r.concept): {
                "valeur": float(r.value),
                "unite": str(r.unit),
                "fin_periode": r.end.date().isoformat(),
                "depose": r.filed.date().isoformat(),
            }
            for r in dernier.itertuples()
        }
        depose = pd.Timestamp(dernier["filed"].max())
        sid = f"xbrl:{ticker}:{depose.date().isoformat()}"
        src = Source(
            source_id=sid,
            type="depot_sec",
            titre=f"Faits XBRL (companyfacts) : {ticker}",
            reference=f"xbrl/{ticker} ; dernier dépôt filed={depose.date().isoformat()}",
            date_publication=depose.tz_localize(UTC)
            if depose.tzinfo is None
            else depose.tz_convert(UTC),
            extrait=str({k: v["valeur"] for k, v in faits.items()})[:EXTRAIT_MAX],
        )
        appel = ToolCall(
            outil="xbrl_facts",
            parametres={"actif": ticker, "concepts": list(faits)},
            resultat=jsonable(faits),
            duree_ms=int((time.perf_counter() - debut) * 1000),
            date_derniere_donnee=depose.date(),
        )
        texte = f"[source_id={sid}] actif={ticker} outil=xbrl_facts\n{faits}"
        ev.items.append(Evidence(src, appel, texte, valeurs_ancrage(faits), ticker, "texte"))
