"""Modèles de données de la couche `data/` (sans dépendance vers un autre module métier)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


class LookAheadError(RuntimeError):
    """Une donnée publiée à la coupure de t ou après a été demandée ou servie."""


class MissingSecretError(RuntimeError):
    """Variable d'environnement absente (seul le NOM de la variable est indiqué, jamais sa valeur)."""


@dataclass(frozen=True)
class Filing:
    ticker: str
    cik: str
    accession: str
    form: str
    filing_date: date
    accepted_utc: datetime  # instant d'acceptation EDGAR, converti en UTC
    report_date: date | None
    primary_document: str
    has_text: bool = False


@dataclass(frozen=True)
class NewsItem:
    item_id: str
    source: str
    published_at: datetime  # UTC ; pour GDELT : date de première observation (seendate)
    title: str
    summary: str
    url: str
    time_semantics: str = "published"  # « published » ou « seendate » (GDELT)
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewsQuery:
    terms: tuple[
        str, ...
    ] = ()  # au moins un terme dans le titre ou le résumé (insensible à la casse)
    tags: tuple[str, ...] = ()  # étiquettes d'ingestion (ticker, requête GDELT)
    sources: tuple[str, ...] = ()
    start: date | None = None
    limit: int | None = None


@dataclass(frozen=True)
class EsgRecord:
    asset_id: str
    score: float | None  # score fournisseur brut (sens : voir config/esg.yaml), None si absent
    score_source: str | None
    exclusions: tuple[str, ...]  # catégories normatives détectées
    exclusion_basis: str | None  # « sic », « vendor_flag », « etf_methodology », None si inconnu
    observed_at: datetime  # instant de collecte (UTC)
    non_point_in_time: bool  # True : donnée non datée, réservée au live ou à la sensibilité
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class QualityIssue:
    kind: str  # gap, duplicate, split, outlier, short_history, stale, currency, non_positive
    severity: str  # info, warning, error
    subject: str
    detail: str
    start: date | None = None
    end: date | None = None
