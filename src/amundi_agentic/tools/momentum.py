# ruff: noqa: E501
"""Momentum, tendance et synthèse Valuation/Momentum (L1 §4).

| Outil | Formule | Unité |
| --- | --- | --- |
| `momentum` (k mois) | P_{t-1} / P_{t-1-n_k} - 1, n_k séances (voir H1) | décimal |
| `momentum_12_1` | P_{t-1-21} / P_{t-1-252} - 1 (Jegadeesh et Titman, 1993 : dernier mois sauté) | décimal |
| `trend_vs_sma` | P_{t-1} / SMA_w - 1, SMA_w = moyenne des w dernières clôtures (dernière incluse) | décimal |

Hypothèses (H) :
* H1 : un mois = 21 séances ; 1, 3, 6 et 12 mois = 21, 63, 126 et 252 séances (cohérent avec la
  base de 252 séances par an du papier). Pas de calendrier civil : moins ambigu en cas de jours fériés.
* H2 : tendance « haussière » si le prix est strictement au-dessus de sa moyenne mobile de 200
  séances, « baissière » s'il est strictement en dessous, « neutre » si égal.
* H3 : `p_{t-1}` désigne la dernière clôture connue avant t (D-038).

Cas limites : historique plus court que le décalage requis -> `InsufficientDataError` ; NaN sur une
des bornes ou dans la moyenne -> `MissingDataError`. `valuation_summary` ne lève pas pour un
indicateur seul : il le place dans `manquants` avec la raison et calcule les autres.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from amundi_agentic.tools import finance
from amundi_agentic.tools.base import (
    DegenerateSeriesError,
    InsufficientDataError,
    MissingDataError,
    ToolError,
    ToolResult,
    known_before,
    make_meta,
    trailing_prices,
)

MONTH_TRADING_DAYS = 21
HORIZONS_MONTHS = (1, 3, 6, 12)


def _borne(prices: pd.Series, as_of: date, lags: tuple[int, ...]) -> pd.Series:
    """Prix aux positions -1-lag (lag en séances) parmi les prix connus ; pas de NaN toléré."""
    connu = known_before(prices, as_of, "prix")
    maxi = max(lags)
    if len(connu) < maxi + 1:
        raise InsufficientDataError(
            f"momentum : {len(connu)} observations avant {as_of}, {maxi + 1} requises"
        )
    pts = connu.iloc[[-1 - lag for lag in lags]].astype(float)
    if pts.isna().any():
        raise MissingDataError("momentum : prix manquant à une borne (aucun remplissage)")
    if (pts <= 0).any():
        raise DegenerateSeriesError("momentum : prix non strictement positif à une borne")
    return pts


def momentum(prices: pd.Series, as_of: date, months: int) -> ToolResult[float]:
    """Rendement sur `months` mois (1, 3, 6 ou 12), en séances (H1)."""
    if months not in HORIZONS_MONTHS:
        raise ValueError(f"horizon en mois parmi {HORIZONS_MONTHS}")
    n = months * MONTH_TRADING_DAYS
    pts = _borne(prices, as_of, (0, n))
    return ToolResult(
        float(pts.iloc[0] / pts.iloc[1] - 1.0),
        make_meta("momentum", as_of, pts.index, 2, months=months, sessions=n),
    )


def momentum_12_1(prices: pd.Series, as_of: date) -> ToolResult[float]:
    """Momentum 12-1 mois : rendement de t-12 mois à t-1 mois, dernier mois exclu."""
    pts = _borne(prices, as_of, (MONTH_TRADING_DAYS, 12 * MONTH_TRADING_DAYS))
    return ToolResult(
        float(pts.iloc[0] / pts.iloc[1] - 1.0),
        make_meta("momentum_12_1", as_of, pts.index, 2),
    )


def trend_vs_sma(prices: pd.Series, as_of: date, window: int = 200) -> ToolResult[dict[str, Any]]:
    """Écart du dernier prix à sa moyenne mobile de `window` séances et sens de la tendance (H2)."""
    w = trailing_prices(prices, as_of, window - 1)  # window clôtures
    sma = float(w.mean())
    ecart = float(w.iloc[-1] / sma - 1.0)
    sens = "haussiere" if ecart > 0 else "baissiere" if ecart < 0 else "neutre"
    return ToolResult(
        {"ecart_sma": ecart, "sma": sma, "tendance": sens},
        make_meta("trend_vs_sma", as_of, w.index, len(w), window=window),
    )


def _mdd_numeric(prices: pd.Series, as_of: date, window: int) -> ToolResult[float]:
    r = finance.max_drawdown(prices, as_of, window)
    return ToolResult(float(r.value["max_drawdown"]), r.meta)  # type: ignore[arg-type]


def valuation_summary(
    prices: pd.Series,
    as_of: date,
    rf_annual: float = 0.0,
    window: int = finance.DEFAULT_WINDOW,
) -> ToolResult[dict[str, Any]]:
    """Tous les indicateurs de l'agent Valuation/Momentum pour un actif, en un seul appel.

    `valeurs` : dictionnaire plat de nombres (décimal) ; `manquants` : indicateur -> raison.
    La date de la dernière donnée est celle de la dernière clôture connue avant t.
    """
    connu = known_before(prices, as_of, "prix")
    valeurs: dict[str, float | str] = {}
    manquants: dict[str, str] = {}

    def essai(nom: str, f) -> None:
        try:
            res = f()
        except ToolError as e:
            manquants[nom] = f"{type(e).__name__} : {e}"
            return
        v = res.value
        if isinstance(v, dict):
            for k, x in v.items():
                valeurs[f"{nom}.{k}"] = x
        else:
            valeurs[nom] = float(v)

    essai("rendement_annualise", lambda: finance.annualized_return(prices, as_of, window))
    essai("volatilite_annualisee", lambda: finance.annualized_volatility(prices, as_of, window))
    essai("sharpe", lambda: finance.sharpe_ratio(prices, as_of, window, rf_annual))
    essai("sortino", lambda: finance.sortino_ratio(prices, as_of, window, rf_annual))
    essai("calmar", lambda: finance.calmar_ratio(prices, as_of, window))
    essai("creux_courant", lambda: finance.current_drawdown(prices, as_of, window))
    essai("perte_maximale", lambda: _mdd_numeric(prices, as_of, window))
    for m in HORIZONS_MONTHS:
        essai(f"momentum_{m}m", lambda m=m: momentum(prices, as_of, m))
    essai("momentum_12_1", lambda: momentum_12_1(prices, as_of))
    essai("tendance_sma200", lambda: trend_vs_sma(prices, as_of, 200))
    return ToolResult(
        {"valeurs": valeurs, "manquants": manquants},
        make_meta(
            "valuation_summary",
            as_of,
            connu.index[-(window + 1) :] if len(connu) else None,
            min(len(connu), window + 1),
            window=window,
            rf_annual=rf_annual,
        ),
    )
