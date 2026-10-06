"""Fournisseurs de données des agents : réel (`PitDataProvider`, `as_of(t)`) et synthétique.

`SyntheticData` produit des séries déterministes (graine fixe) POUR LES TESTS ET LA COMMANDE
`--mock` : ce ne sont pas des données de marché. Il génère volontairement des barres à t et après
(et des publications postérieures) pour que le filtre point-in-time soit réellement exercé.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from amundi_agentic.data.models import EsgRecord, NewsItem, NewsQuery
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.universe import Candidate, Universe
from amundi_agentic.tools.base import ToolResult, known_before, make_meta

DEMO_RF = 0.04


def _graine(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def classes_et_tickers(universe: Universe) -> tuple[dict[str, str], dict[str, str]]:
    """(classe -> ticker primaire, ticker -> classe), lus dans `config/universe.yaml`."""
    classes = {n: c.primary.ticker for n, c in universe.classes.items()}
    inverse: dict[str, str] = {}
    for n, c in universe.classes.items():
        inverse[c.primary.ticker] = n
        if c.proxy:
            inverse[c.proxy.ticker] = n
        for a in c.alternatives:
            inverse[a.ticker] = n
    return classes, inverse


class SyntheticData:
    """Données synthétiques déterministes, filtrées à t comme `as_of(t)`."""

    def __init__(
        self,
        t: date,
        *,
        stocks: Sequence[str] = ("AAA", "BBB", "CCC"),
        n_jours: int = 1100,
        graine: int = 0,
        universe: Universe | None = None,
        esg_exclus: Sequence[str] = (),
        avec_news: bool = True,
    ) -> None:
        self.t = t
        self.stocks = list(stocks)
        self.graine = graine
        self.universe = universe or Universe.load()
        self._classes, self._ticker_class = classes_et_tickers(self.universe)
        self._n = n_jours
        self._esg_exclus = set(esg_exclus)
        self._avec_news = avec_news
        self._esg_rules = load_yaml("esg.yaml")["normative_exclusions"]
        self._prix: dict[str, pd.Series] = {}

    @property
    def classes(self) -> dict[str, str]:
        return dict(self._classes)

    @property
    def ticker_class(self) -> dict[str, str]:
        return dict(self._ticker_class)

    # ------------------------------------------------------------------ prix
    def _serie(self, ticker: str) -> pd.Series:
        """Marche aléatoire sur les jours ouvrés jusqu'à t + 40 jours (le futur est filtré ensuite)."""
        if ticker not in self._prix:
            rng = np.random.default_rng(_graine(self.graine, ticker))
            fin = pd.Timestamp(self.t) + pd.Timedelta(days=40)
            idx = pd.bdate_range(end=fin, periods=self._n)
            mu = rng.uniform(0.0001, 0.0006)
            sig = rng.uniform(0.004, 0.018)
            r = rng.normal(mu, sig, size=len(idx) - 1)
            px = 100 * np.concatenate([[1.0], np.cumprod(1 + r)])
            self._prix[ticker] = pd.Series(px, index=idx, name=ticker)
        return self._prix[ticker]

    def _avant_t(self, ticker: str) -> pd.Series:
        s = self._serie(ticker)
        return s[s.index < pd.Timestamp(self.t)].copy()

    def class_prices(self, asset_class: str) -> pd.Series:
        return self._avant_t(self._classes[asset_class])

    def stock_prices(self, ticker: str) -> pd.Series:
        return self._avant_t(ticker)

    # ------------------------------------------------------------------ macro
    def _macro(self, sid: str) -> pd.DataFrame:
        rng = np.random.default_rng(_graine(self.graine, sid))
        fin = pd.Timestamp(self.t) + pd.Timedelta(days=60)
        quotidien = {
            "fred:DGS10": (4.0, 0.02), "fred:DGS2": (3.6, 0.02), "fred:T10Y2Y": (0.4, 0.01),
            "fred:BAMLH0A0HYM2": (3.5, 0.03), "fred:VIXCLS": (16.0, 0.4),
            "ecb:YC_SPOT_10Y": (2.6, 0.02), "ecb:YC_SPOT_2Y": (2.2, 0.02), "ecb:ESTR": (3.0, 0.005),
            "fred:DGS1MO": (DEMO_RF * 100, 0.005),
        }  # fmt: skip
        if sid in quotidien:
            base, vol = quotidien[sid]
            d = pd.bdate_range(end=fin, periods=900)
            v = base + np.cumsum(rng.normal(0, vol, len(d)))
            retard = pd.Timedelta(days=1)
        elif sid == "fred:GDPC1":
            d = pd.date_range(end=fin, periods=24, freq="QS")
            v = 20000 * (1.006 ** np.arange(len(d)))
            retard = pd.Timedelta(days=115)
        elif sid == "fred:CPIAUCSL":
            d = pd.date_range(end=fin, periods=60, freq="MS")
            v = 250 * (1.0025 ** np.arange(len(d)))
            retard = pd.Timedelta(days=45)
        elif sid == "fred:UNRATE":
            d = pd.date_range(end=fin, periods=60, freq="MS")
            v = 4.0 + np.cumsum(rng.normal(0, 0.05, len(d)))
            retard = pd.Timedelta(days=35)
        else:
            raise KeyError(f"série macro synthétique inconnue : {sid}")
        out = pd.DataFrame({"date": d, "value": v, "available_from": d + retard})
        return out[out["available_from"] < pd.Timestamp(self.t)].reset_index(drop=True)

    def macro_series(self, series_ids: Sequence[str]):
        sortie: dict[str, pd.DataFrame] = {}
        absentes: dict[str, str] = {}
        for sid in series_ids:
            try:
                sortie[sid] = self._macro(sid)
            except KeyError as e:
                absentes[sid] = str(e)
        return sortie, absentes

    def risk_free_annual(self) -> ToolResult[float] | None:
        df = self._macro("fred:DGS1MO")
        d = df[df["date"] < pd.Timestamp(self.t)]
        if d.empty:
            return None
        return ToolResult(
            float(d["value"].iloc[-1]) / 100.0,
            make_meta("risk_free_annual", self.t, d["date"].iloc[-1:], 1, series="fred:DGS1MO"),
        )

    # ------------------------------------------------------------------ news, dépôts, ESG
    def news(self, query: NewsQuery) -> list[NewsItem]:
        if not self._avec_news:
            return []
        tag = query.tags[0] if query.tags else "marche"
        sortie = []
        for k in range(1, 9):
            pub = datetime(self.t.year, self.t.month, self.t.day, tzinfo=UTC) - timedelta(
                days=2 * k
            )
            sortie.append(
                NewsItem(
                    item_id=f"synth-{tag}-{k}",
                    source="synthetique",
                    published_at=pub,
                    title=f"Actualité synthétique {k} sur {tag}",
                    summary="Texte de test sans valeur d'information.",
                    url=f"https://exemple.invalid/{tag}/{k}",
                    tags=(tag,),
                )
            )
        # un article publié APRÈS t : le filtre point-in-time doit l'écarter (jamais servi)
        return [
            n
            for n in sortie
            if n.published_at < datetime(self.t.year, self.t.month, self.t.day, tzinfo=UTC)
        ]

    def xbrl_facts(self, ticker: str) -> pd.DataFrame | None:
        rng = np.random.default_rng(_graine(self.graine, ticker, "xbrl"))
        filed = pd.Timestamp(self.t) - pd.Timedelta(days=45)
        return pd.DataFrame(
            {
                "concept": ["Revenues", "NetIncomeLoss", "OperatingIncomeLoss"],
                "unit": ["USD"] * 3,
                "start": [filed - pd.Timedelta(days=365)] * 3,
                "end": [filed - pd.Timedelta(days=30)] * 3,
                "value": [
                    float(rng.integers(1_000, 9_000)) * 1e6,
                    float(rng.integers(-500, 900)) * 1e6,
                    float(rng.integers(-300, 1_200)) * 1e6,
                ],
                "accn": ["0000000000-00-000001"] * 3,
                "fy": [self.t.year - 1] * 3,
                "fp": ["FY"] * 3,
                "form": ["10-K"] * 3,
                "filed": [filed] * 3,
            }
        )

    def esg(self, asset_id: str) -> EsgRecord | None:
        exclu = asset_id in self._esg_exclus
        kind_etf = asset_id in self._ticker_class
        return EsgRecord(
            asset_id=asset_id,
            score=None,
            score_source=None,
            exclusions=("tobacco",) if exclu else (),
            exclusion_basis=None if kind_etf else "sic",
            observed_at=datetime(self.t.year, self.t.month, self.t.day, tzinfo=UTC)
            - timedelta(days=30),
            non_point_in_time=False,
            notes=() if kind_etf else ("no_vendor_score",),
        )

    def etf_esg(self) -> Any | None:
        return None

    def esg_rules(self) -> dict[str, Any]:
        return self._esg_rules


class PitDataProvider:
    """Fournisseur réel : couche `data/` (`as_of(t)`), prix en EUR, source ESG manuelle par ETF."""

    def __init__(
        self, view: Any, universe: Universe | None = None, etf_view: Any | None = None
    ) -> None:
        from amundi_agentic.tools.market_data import MarketDataAdapter

        self.view = view
        self.t: date = view.t
        self.universe = universe or Universe.load()
        self._classes, self._ticker_class = classes_et_tickers(self.universe)
        self._adapter = MarketDataAdapter(view)
        self._etf_view = etf_view
        self._rules = load_yaml("esg.yaml")["normative_exclusions"]

    @property
    def classes(self) -> dict[str, str]:
        return dict(self._classes)

    @property
    def ticker_class(self) -> dict[str, str]:
        return dict(self._ticker_class)

    def _prix(self, cand: Candidate) -> pd.Series:
        s = self._adapter.prices_eur([cand])[cand.ticker].dropna()
        return known_before(s, self.t, cand.ticker)

    def class_prices(self, asset_class: str) -> pd.Series:
        return self._prix(self.universe.classes[asset_class].primary)

    def stock_prices(self, ticker: str) -> pd.Series:
        return self._prix(Candidate("titre", ticker, "USD", "primary"))

    def macro_series(self, series_ids: Sequence[str]):
        return self._adapter.macro_series(series_ids)

    def risk_free_annual(self) -> ToolResult[float] | None:
        try:
            return self._adapter.risk_free_annual()
        except Exception:  # noqa: BLE001 - taux absent : signalé par l'agent, jamais inventé
            return None

    def news(self, query: NewsQuery) -> list[NewsItem]:
        return self.view.news(query)

    def xbrl_facts(self, ticker: str) -> pd.DataFrame | None:
        try:
            return self.view.xbrl_facts(ticker)
        except KeyError:
            return None

    def esg(self, asset_id: str) -> EsgRecord | None:
        return self.view.esg(asset_id)

    def etf_esg(self) -> Any | None:
        return self._etf_view

    def esg_rules(self) -> dict[str, Any]:
        return self._rules


def rag_synthetique(t: date, stocks: Sequence[str]):
    """RAG factice pour `--mock` et les tests : un passage de 10-K par section et par titre
    (texte de test sans valeur d'information, daté 45 jours avant t)."""
    from amundi_agentic.agents.ports import FakePassage, FakeRagTool
    from amundi_agentic.schemas import Source

    publie = datetime(t.year, t.month, t.day, tzinfo=UTC) - timedelta(days=45)
    passages: dict[str, list[FakePassage]] = {}
    for tk in stocks:
        lot = []
        for i, section in enumerate(("Item 7 (MD&A)", "Item 1A (Risk Factors)", "Item 8")):
            texte = f"Passage de test {i} du 10-K de {tk} : la direction commente l'activité."
            lot.append(
                FakePassage(
                    text=texte,
                    section=section,
                    score=1.0 - 0.1 * i,
                    source=Source(
                        source_id=f"depot_sec:{tk}:10-K:{i}",
                        type="depot_sec",
                        titre=f"10-K {tk} : {section}",
                        reference=f"synthetique://{tk}/10-K",
                        date_publication=publie,
                        extrait=texte,
                    ),
                )
            )
        passages[tk] = lot
    return FakeRagTool(passages=passages)
