"""Adaptateur mince entre `amundi_agentic.data` (accès `as_of(t)`) et les outils purs.

Il ne refait AUCUNE logique point-in-time : les séries viennent de `DataView` (prix de séances
strictement antérieures à t, macro à `available_from` < t, fixings BCE connus à t). Il assemble
seulement les entrées des outils (panel de prix en EUR, taux sans risque, tableaux macro) et rend
visibles les trous (liste des séries absentes, comptes de conversion de change). Les outils
réappliquent de toute façon la coupure t : une erreur d'assemblage ne peut pas introduire de futur.

Conventions : prix en EUR (D-038, L1 §9.1) ; taux sans risque = DGS1MO (L1 §9.3, config/data.yaml)
en décimal annuel (la série FRED est en pourcents).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd

from amundi_agentic.data.pit import DataView
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.universe import Candidate, Universe, convert_to_eur
from amundi_agentic.tools.base import (
    MissingDataError,
    ToolResult,
    check_as_of,
    known_macro,
    make_meta,
)

RISK_FREE_SERIES = "fred:DGS1MO"
REFERENCE_CURRENCY = "EUR"


class MarketDataAdapter:
    """Récupère, pour une date t, les séries nécessaires aux outils (lecture seule)."""

    def __init__(self, view: DataView, max_stale_days: int | None = None) -> None:
        self.view = view
        if max_stale_days is None:
            max_stale_days = int(load_yaml("data.yaml")["ecb"]["fx_max_stale_days"])
        self.max_stale_days = max_stale_days
        self.fx_counts: dict[str, dict[str, int]] = {}

    @property
    def as_of(self) -> date:
        return self.view.t

    def prices_eur(
        self, candidates: Sequence[Candidate], start: date | None = None
    ) -> pd.DataFrame:
        """Clôtures ajustées en EUR, une colonne par ticker. Un fixing trop ancien donne NaN."""
        colonnes: dict[str, pd.Series] = {}
        for c in candidates:
            px = self.view.prices([c.ticker], start=start)[c.ticker]
            if c.currency == REFERENCE_CURRENCY:
                colonnes[c.ticker] = px
                continue
            fx = self.view.fx_eur(c.currency, start=start)
            eur, comptes = convert_to_eur(px, fx, self.max_stale_days)
            colonnes[c.ticker] = eur
            self.fx_counts[c.ticker] = comptes
        return pd.DataFrame(colonnes).sort_index()

    def primary_prices_eur(self, universe: Universe, start: date | None = None) -> pd.DataFrame:
        """Panel des ETF primaires de chaque classe (L1 §9.1), en EUR."""
        return self.prices_eur([c.primary for c in universe.classes.values()], start=start)

    def macro_series(
        self, series_ids: Sequence[str]
    ) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
        """Tableaux `macro_long` connus à t ; une série absente est listée, jamais inventée."""
        out: dict[str, pd.DataFrame] = {}
        absentes: dict[str, str] = {}
        for sid in series_ids:
            try:
                out[sid] = self.view.macro_long(sid)
            except KeyError as e:
                absentes[sid] = str(e)
        return out, absentes

    def risk_free_annual(self, window_start: date | None = None) -> ToolResult[float]:
        """Taux sans risque annuel (décimal) : DGS1MO / 100.

        `window_start` None : dernière valeur connue ; sinon moyenne des observations de
        [window_start, t) (celles de la fenêtre de calcul du Sharpe). Aucune observation : erreur.
        """
        check_as_of(self.as_of)
        k = known_macro(self.view.macro_long(RISK_FREE_SERIES), self.as_of, RISK_FREE_SERIES)
        if window_start is not None:
            k = k[k["date"] >= pd.Timestamp(window_start)]
        if k.empty:
            raise MissingDataError(
                f"{RISK_FREE_SERIES} : aucune observation connue dans la fenêtre"
            )
        valeur = float(k["value"].iloc[-1] if window_start is None else k["value"].mean()) / 100.0
        return ToolResult(
            valeur,
            make_meta(
                "risk_free_annual",
                self.as_of,
                k["date"],
                len(k),
                series=RISK_FREE_SERIES,
                mode="dernier" if window_start is None else "moyenne",
            ),
        )
