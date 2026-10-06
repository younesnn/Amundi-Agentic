# ruff: noqa: E501, N806, N818
"""Sources de données de la réplication : stockage réel (lecture seule) ou synthétique (tests, mock).

Deux usages strictement séparés (D-065, séparation décision / performance) :

* `fournisseur_decision()` : données connues à t (strictement antérieures), enveloppées par
  `GardeFuture`, qui lève `LookAheadError` si une série, un tableau ou un article servi à un agent
  porte une date >= t ;
* `prix_suivi()` / `taux_suivi()` : prix et taux servis comme `as_of(cible.as_of_performance)`
  (donc jusqu'à `fin_suivi` inclus, jamais au-delà), appelés SEULEMENT par la mesure après coup.

L'utilisabilité d'un titre (`eligibilite`) ne lit que des dates et des comptes de séances, jamais une
valeur de cours après t.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from amundi_agentic.agents.ports import FakeNewsSummaryTool, NewsSummaryTool, RagTool
from amundi_agentic.agents.providers import (
    PitDataProvider,
    SyntheticData,
    construire_outils_reels,
    rag_synthetique,
)
from amundi_agentic.data.models import LookAheadError
from amundi_agentic.data.universe import Universe
from amundi_agentic.evaluation.repl_config import ReplicationConfig


# ------------------------------------------------------------------------------- garde anti-futur
class GardeFuture:
    """Enveloppe d'un `DataProvider` : toute donnée servie doit être antérieure à t.

    Le contrôle est indépendant de la couche de données (ceinture et bretelles) : si un fournisseur
    laissait passer une barre, un tableau macro, un fait XBRL ou une news datés de t ou après,
    l'appel échoue (`LookAheadError`) au lieu de nourrir un agent avec du futur.
    """

    def __init__(self, inner: Any, t: date) -> None:
        self._inner = inner
        self._t = t
        self.t = t
        self.n_controles = 0
        self.date_max_servie: pd.Timestamp | None = None

    def __getattr__(self, nom: str) -> Any:
        attr = getattr(self._inner, nom)
        if not callable(attr):
            return attr

        def appel(*a: Any, **k: Any) -> Any:
            res = attr(*a, **k)
            self._verifier(res, nom)
            return res

        return appel

    def _noter(self, d: Any) -> None:
        ts = pd.Timestamp(d)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        if self.date_max_servie is None or ts > self.date_max_servie:
            self.date_max_servie = ts

    def _refuser(self, nom: str, d: Any) -> None:
        raise LookAheadError(f"{nom} : donnée datée du {d} servie à un agent (t = {self._t})")

    def _verifier(self, obj: Any, nom: str) -> None:
        self.n_controles += 1
        t_ts = pd.Timestamp(self._t)
        if isinstance(obj, pd.Series):
            if len(obj) and isinstance(obj.index, pd.DatetimeIndex):
                self._noter(obj.index.max())
                if obj.index.max() >= t_ts:
                    self._refuser(nom, obj.index.max())
        elif isinstance(obj, pd.DataFrame):
            if len(obj) and isinstance(obj.index, pd.DatetimeIndex):
                self._noter(obj.index.max())
                if obj.index.max() >= t_ts:
                    self._refuser(nom, obj.index.max())
            for col in ("date", "available_from", "filed"):
                if col in obj.columns and len(obj):
                    mx = pd.Timestamp(obj[col].max())
                    self._noter(mx)
                    if mx >= t_ts:
                        self._refuser(f"{nom}[{col}]", mx)
        elif isinstance(obj, dict):
            for v in obj.values():
                self._verifier(v, nom)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                self._verifier(v, nom)
        elif hasattr(obj, "published_at"):  # NewsItem
            pub = obj.published_at
            self._noter(pub)
            if pub >= datetime(self._t.year, self._t.month, self._t.day, tzinfo=UTC):
                self._refuser(nom, pub)
        elif hasattr(obj, "observed_at") and getattr(obj, "observed_at", None) is not None:
            obs = obj.observed_at  # EsgRecord
            if not getattr(obj, "non_point_in_time", False):
                self._noter(obs)
                if obs >= datetime(self._t.year, self._t.month, self._t.day, tzinfo=UTC):
                    self._refuser(nom, obs)


# ------------------------------------------------------------------------------- protocole
@dataclass
class EtatPool:
    pool: list[str]
    utilisables: list[str]
    exclus: dict[str, str]  # titre -> motif (publié)


class SourceReplication(Protocol):
    synthetique: bool

    def pool(self) -> list[str]: ...

    def eligibilite(self, ticker: str, cfg: ReplicationConfig) -> tuple[bool, str]: ...

    def depots_texte(self, ticker: str, t: date) -> int | None: ...

    def fournisseur_decision(self, titres: list[str], t: date) -> Any: ...

    def outils(
        self, llm: Any, fournisseur: Any, titres: list[str]
    ) -> tuple[RagTool | None, NewsSummaryTool | None, list[str]]: ...

    def prix_suivi(self, titres: list[str], cfg: ReplicationConfig) -> pd.DataFrame: ...

    def taux_suivi(self, cfg: ReplicationConfig) -> pd.Series: ...

    def manifeste(self) -> str | None: ...


def etat_pool(source: SourceReplication, cfg: ReplicationConfig) -> EtatPool:
    """Pool daté : utilisables et exclus avec motif (règle fixée d'avance, publiée)."""
    pool = sorted(source.pool())
    utilisables: list[str] = []
    exclus: dict[str, str] = {}
    for tk in pool:
        ok, motif = source.eligibilite(tk, cfg)
        if cfg.pool.depots_texte_requis and ok:
            n = source.depots_texte(tk, cfg.cible.date_decision)
            if not n:
                ok, motif = False, "aucun texte de dépôt 10-K ou 10-Q dans le stockage"
        (utilisables.append(tk) if ok else exclus.__setitem__(tk, motif))
    return EtatPool(pool, utilisables, exclus)


# ------------------------------------------------------------------------------- source réelle
class SourceReelle:
    """Stockage point-in-time local (`.cache/data/store`, ou `AMUNDI_DATA_DIR`), lecture seule."""

    synthetique = False

    def __init__(self, universe: Universe | None = None, rag_dir: Path | None = None) -> None:
        from amundi_agentic.data.pit import PointInTimeStore
        from amundi_agentic.data.settings import ROOT, DataSettings
        from amundi_agentic.data.store import ParquetStore

        self.universe = universe or Universe.load()
        self._settings = DataSettings.load()
        self._store = ParquetStore(self._settings.store_dir, self._settings.snapshot_dir)
        self._pit = PointInTimeStore(self._store, self._settings.config)
        import os

        self._rag_dir = rag_dir or Path(os.environ.get("AMUNDI_RAG_DIR", ROOT / ".cache" / "rag"))

    def pool(self) -> list[str]:
        df = self._store.read("universe/pool")
        if df is None:
            raise KeyError(
                "jeu de données absent du stockage : universe/pool (data fetch --sources pool)"
            )
        return list(df["ticker"])

    def eligibilite(self, ticker: str, cfg: ReplicationConfig) -> tuple[bool, str]:
        t = cfg.cible.date_decision
        vt = self._pit.as_of(
            t
        )  # SEULES des données connues à t : jamais de séance de suivi (revue B1)
        try:
            s = vt.prices([ticker])[ticker].dropna()
        except KeyError:
            return (
                False,
                "aucune donnée de prix dans le stockage (société radiée ou absente de la source)",
            )
        avant = s[s.index < pd.Timestamp(t)]
        if len(avant) < cfg.pool.barres_min_historique:
            return (
                False,
                f"historique insuffisant : {len(avant)} séances avant t, {cfg.pool.barres_min_historique} requises",
            )
        janv = avant[avant.index >= pd.Timestamp(t) - pd.Timedelta(days=31)]
        if len(janv) < cfg.pool.barres_min_janvier:
            return (
                False,
                f"prix insuffisants dans les 31 jours avant t : {len(janv)} séances, {cfg.pool.barres_min_janvier} requises",
            )
        if cfg.pool.depot_requis_avant_t:
            try:
                deps = vt.filings(ticker, set(cfg.pool.formulaires))
            except KeyError:
                return False, "index EDGAR absent du stockage"
            if not deps:
                return False, f"aucun dépôt {'/'.join(cfg.pool.formulaires)} accepté avant t"
        return True, "utilisable"

    def depots_texte(self, ticker: str, t: date) -> int | None:
        """Nombre de dépôts 10-K ou 10-Q dont le TEXTE est dans le stockage, acceptés avant t."""
        try:
            deps = self._pit.as_of(t).filings(ticker, {"10-K", "10-Q"})
        except KeyError:
            return 0
        return sum(1 for d in deps if d.has_text)

    def fournisseur_decision(self, titres: list[str], t: date) -> GardeFuture:
        etf_view = None
        try:
            from amundi_agentic.data.connectors.esg_etf_sources import load_for_universe

            etf_view = load_for_universe().as_of(t)
        except Exception:  # noqa: BLE001 - source manuelle absente : états « inconnu », sans effet sur les titres
            etf_view = None
        return GardeFuture(PitDataProvider(self._pit.as_of(t), self.universe, etf_view), t)

    def outils(self, llm: Any, fournisseur: Any, titres: list[str]):
        rag, resume, av = construire_outils_reels(llm, fournisseur, self._rag_dir)
        return rag, resume, av

    def prix_suivi(self, titres: list[str], cfg: ReplicationConfig) -> pd.DataFrame:
        """Clôtures de [t, fin_suivi] servies comme `as_of(as_of_performance)`."""
        vp = self._pit.as_of(cfg.cible.as_of_performance)
        df = vp.prices(list(titres), start=cfg.cible.date_decision, field=cfg.cible.prix)
        if len(df) and df.index.max() > pd.Timestamp(cfg.cible.fin_suivi):
            raise LookAheadError("prix postérieurs à fin_suivi servis à la mesure de performance")
        df = df.loc[df.index <= pd.Timestamp(cfg.cible.fin_suivi)]
        # titre sans AUCUNE clôture dans le suivi (radié avant t + 1) : dernière clôture connue à t,
        # posée sur la première séance (position gelée, règle `titre_sans_prix_en_fin_de_suivi`)
        for tk in [c for c in df.columns if df[c].isna().all()]:
            avant = (
                self._pit.as_of(cfg.cible.date_decision)
                .prices([tk], field=cfg.cible.prix)[tk]
                .dropna()
            )
            if len(avant) and len(df):
                df.loc[df.index[0], tk] = float(avant.iloc[-1])
        return df

    def taux_suivi(self, cfg: ReplicationConfig) -> pd.Series:
        vp = self._pit.as_of(cfg.cible.as_of_performance)
        long = vp.macro_long(cfg.taux_sans_risque.serie)
        s = long.set_index("date")["value"].sort_index()
        return s.loc[s.index <= pd.Timestamp(cfg.cible.fin_suivi)]

    def manifeste(self) -> str | None:
        try:
            from amundi_agentic.data.manifest import data_manifest

            return str(data_manifest(self._settings)["manifest_sha256"])
        except Exception:  # noqa: BLE001 - manifeste indisponible : signalé, non bloquant
            return None


# ------------------------------------------------------------------------------- source synthétique
def _graine(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def marche_synthetique(ticker: str, graine: int, debut: str, fin: str) -> pd.Series:
    """Marche aléatoire déterministe sur un calendrier absolu de jours ouvrés. PAS des données de
    marché : sert à exercer la mécanique. Le calendrier va au-delà de `fin_suivi` pour que les
    garde-fous (aucun prix postérieur) soient réellement exercés."""
    idx = pd.bdate_range(debut, fin)
    rng = np.random.default_rng(_graine(graine, ticker, "marche"))
    mu, sig = rng.uniform(0.0001, 0.0008), rng.uniform(0.006, 0.02)
    r = rng.normal(mu, sig, size=len(idx) - 1)
    return pd.Series(100 * np.concatenate([[1.0], np.cumprod(1 + r)]), index=idx, name=ticker)


class _DonneesSynthetiques(SyntheticData):
    """`SyntheticData` dont les séries sont celles de `marche_synthetique` (même monde avant t et
    après t : la mesure de performance prolonge les prix vus par les agents)."""

    def __init__(self, t: date, *, stocks: list[str], graine: int, fin: str, universe: Universe):
        super().__init__(t, stocks=stocks, graine=graine, universe=universe)
        self._fin = fin

    def _serie(self, ticker: str) -> pd.Series:
        if ticker not in self._prix:
            self._prix[ticker] = marche_synthetique(ticker, self.graine, "2021-01-04", self._fin)
        return self._prix[ticker]


class SourceSynthetique:
    """Pool synthétique : `n_pool` titres dont les `sans_donnees` dernières n'ont aucune donnée de
    prix (comme ANSS et JNPR dans le stockage réel), plus le titre hors pool."""

    synthetique = True

    def __init__(
        self,
        cfg: ReplicationConfig,
        *,
        n_pool: int = 24,
        sans_donnees: int = 2,
        arrets: dict[str, str] | None = None,
        graine: int = 0,
        universe: Universe | None = None,
    ) -> None:
        self.cfg = cfg
        self.arrets = dict(arrets or {})  # titre -> dernière date de prix (radiation simulée)
        self.graine = graine
        self.universe = universe or Universe.load()
        self._tickers = [f"SYN{i:02d}" for i in range(1, n_pool + 1)]
        self._sans = set(self._tickers[n_pool - sans_donnees :]) if sans_donnees else set()
        fin = pd.Timestamp(cfg.cible.as_of_performance) + pd.Timedelta(days=60)
        self._fin = fin.strftime("%Y-%m-%d")

    def pool(self) -> list[str]:
        return list(self._tickers)

    def eligibilite(self, ticker: str, cfg: ReplicationConfig) -> tuple[bool, str]:
        if ticker in self._sans:
            return (
                False,
                "aucune donnée de prix dans le stockage (société radiée ou absente de la source)",
            )
        return True, "utilisable"

    def depots_texte(self, ticker: str, t: date) -> int | None:
        return 0 if ticker in self._sans else 3

    def fournisseur_decision(self, titres: list[str], t: date) -> GardeFuture:
        d = _DonneesSynthetiques(
            t, stocks=list(titres), graine=self.graine, fin=self._fin, universe=self.universe
        )
        return GardeFuture(d, t)

    def outils(self, llm: Any, fournisseur: Any, titres: list[str]):
        return rag_synthetique(fournisseur.t, titres), FakeNewsSummaryTool(), []

    def prix_suivi(self, titres: list[str], cfg: ReplicationConfig) -> pd.DataFrame:
        as_of = pd.Timestamp(cfg.cible.as_of_performance)
        cols = {}
        for tk in titres:
            s = marche_synthetique(tk, self.graine, "2021-01-04", self._fin)
            s = s[s.index < as_of]  # servi comme as_of(as_of_performance) : jamais plus loin
            s = s[s.index >= pd.Timestamp(cfg.cible.date_decision)]
            if tk in self.arrets:
                s = s[s.index <= pd.Timestamp(self.arrets[tk])]
            cols[tk] = s
        df = pd.DataFrame(cols).sort_index()
        return df.loc[df.index <= pd.Timestamp(cfg.cible.fin_suivi)]

    def taux_suivi(self, cfg: ReplicationConfig) -> pd.Series:
        idx = pd.bdate_range(
            pd.Timestamp(cfg.cible.date_decision) - pd.Timedelta(days=20), cfg.cible.fin_suivi
        )
        rng = np.random.default_rng(_graine(self.graine, "dgs1mo"))
        return pd.Series(5.30 + np.cumsum(rng.normal(0, 0.01, len(idx))), index=idx)

    def manifeste(self) -> str | None:
        return None


@dataclass
class OutilsDebat:
    rag: RagTool | None
    resume: NewsSummaryTool | None
    avertissements: list[str] = field(default_factory=list)


Fabrique = Callable[[], SourceReplication]
