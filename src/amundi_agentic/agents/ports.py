"""Interfaces (protocoles) entre les agents et ce qui leur fournit des données ou des outils.

* `RagTool`, `NewsSummaryTool` : outils de la tâche A (RAG sur les dépôts, résumé avec réflexion),
  définis ici pour que `agents/` n'importe pas `tools/rag.py` ni `tools/summarize.py`. Les
  implémentations réelles les satisfont par typage structurel ; des versions factices servent aux tests.
* `DataProvider` : tout ce qu'un agent lit, déjà filtré point-in-time à la date t. Deux
  implémentations : `PitDataProvider` (couche `data/`, `as_of(t)`) et `SyntheticData`
  (`agents/synthetic.py`, données de test déterministes).

Les agents ne lisent jamais autre chose que ces interfaces (EX-O1-16).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from amundi_agentic.data.models import EsgRecord, NewsItem, NewsQuery
from amundi_agentic.schemas import Source
from amundi_agentic.tools.base import EXTRAIT_MAX, ToolResult

# ----------------------------------------------------------------------------- outils de la tâche A


class RagPassage(Protocol):
    text: str
    section: str
    score: float
    source: Source


class RagResult(Protocol):
    passages: Sequence[RagPassage]


@runtime_checkable
class RagTool(Protocol):
    def index_filings(self, ticker: str, as_of: date) -> int: ...

    def query(self, ticker: str, question: str, as_of: date, *, k: int = 5) -> RagResult: ...


class NewsSummary(Protocol):
    summary: str
    key_points: Sequence[str]
    sources: Sequence[Source]
    n_calls: int


@runtime_checkable
class NewsSummaryTool(Protocol):
    def __call__(
        self,
        llm: Any,
        items: Sequence[NewsItem],
        as_of: date,
        *,
        focus: str,
        reflection_rounds: int = 1,
        tier: str = "light",
    ) -> NewsSummary: ...


# --- implémentations factices (tests, `--mock`) ------------------------------------------------


@dataclass(frozen=True)
class FakePassage:
    text: str
    section: str
    score: float
    source: Source


@dataclass(frozen=True)
class FakeRagResult:
    passages: tuple[FakePassage, ...]


@dataclass
class FakeRagTool:
    """RAG factice : renvoie les mêmes passages pour toute question d'un titre."""

    passages: dict[str, list[FakePassage]] = field(default_factory=dict)
    indexed: list[tuple[str, date]] = field(default_factory=list)
    queries: list[tuple[str, str, date, int]] = field(default_factory=list)

    def index_filings(self, ticker: str, as_of: date) -> int:
        self.indexed.append((ticker, as_of))
        return len(self.passages.get(ticker, []))

    def query(self, ticker: str, question: str, as_of: date, *, k: int = 5) -> FakeRagResult:
        self.queries.append((ticker, question, as_of, k))
        return FakeRagResult(tuple(self.passages.get(ticker, [])[:k]))


@dataclass(frozen=True)
class FakeNewsSummary:
    summary: str
    key_points: tuple[str, ...]
    sources: tuple[Source, ...]
    n_calls: int = 0


@dataclass
class FakeNewsSummaryTool:
    """Résumé factice : texte fixe, sources = une par article reçu. N'appelle pas le LLM."""

    texte: str = "Résumé factice des actualités."
    appels: list[dict[str, Any]] = field(default_factory=list)

    def __call__(
        self,
        llm: Any,
        items: Sequence[NewsItem],
        as_of: date,
        *,
        focus: str,
        reflection_rounds: int = 1,
        tier: str = "light",
    ) -> FakeNewsSummary:
        self.appels.append({"n_items": len(items), "focus": focus, "as_of": as_of, "tier": tier})
        sources = tuple(
            Source(
                source_id=f"news:{i.item_id}",
                type="news",
                titre=i.title or i.item_id,
                reference=i.url or i.item_id,
                date_publication=i.published_at,
                extrait=(i.summary or i.title or "")[:EXTRAIT_MAX] or "n/a",
            )
            for i in items
        )
        return FakeNewsSummary(self.texte, ("point clé factice",), sources, 0)


# ----------------------------------------------------------------------------- accès aux données


@runtime_checkable
class DataProvider(Protocol):
    """Données lues par les agents, déjà coupées point-in-time à `t` (aucune donnée à t ou après)."""

    t: date

    @property
    def classes(self) -> dict[str, str]:
        """Classe d'actifs -> ticker primaire, lu dans `config/universe.yaml`."""
        ...

    @property
    def ticker_class(self) -> dict[str, str]:
        """Ticker (primaire, proxy, alternative) -> classe d'actifs, lu dans `config/universe.yaml`."""
        ...

    def class_prices(self, asset_class: str) -> pd.Series:
        """Clôtures en EUR de l'ETF primaire de la classe, séances strictement antérieures à t."""
        ...

    def stock_prices(self, ticker: str) -> pd.Series: ...

    def macro_series(
        self, series_ids: Sequence[str]
    ) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
        """Tableaux `macro_long` connus à t ; séries absentes -> raison (jamais inventées)."""
        ...

    def risk_free_annual(self) -> ToolResult[float] | None: ...

    def news(self, query: NewsQuery) -> list[NewsItem]: ...

    def xbrl_facts(self, ticker: str) -> pd.DataFrame | None: ...

    def esg(self, asset_id: str) -> EsgRecord | None: ...

    def etf_esg(self) -> Any | None:
        """Vue point-in-time de la source ESG manuelle par ETF (`EtfEsgView`), ou None."""
        ...

    def esg_rules(self) -> dict[str, Any]:
        """`normative_exclusions` de `config/esg.yaml` (libellés des critères)."""
        ...


def ticker_asset_filter(data: DataProvider, assets: Sequence[str]) -> dict[str, str]:
    """Pour chaque classe de `assets`, son ticker primaire (erreur si la classe est inconnue)."""
    sortie: dict[str, str] = {}
    for a in assets:
        if a not in data.classes:
            raise KeyError(f"classe d'actifs inconnue : {a!r}")
        sortie[a] = data.classes[a]
    return sortie
