# ruff: noqa: E501
"""Valuation : formules du papier AlphaAgents (fiche §5), Sortino, perte maximale, Calmar.

Convention de fenêtre : `window` = nombre n de RENDEMENTS quotidiens, donc n + 1 clôtures, les n + 1
dernières séances strictement antérieures à t (D-038). Rendements simples, en décimal.

| Outil | Formule | Unité |
| --- | --- | --- |
| `cumulative_return` | R = P_n / P_0 - 1 (produit des (1 + r_k) - 1) | décimal |
| `annualized_return` | (1 + R)^(252 / n) - 1 (papier) | décimal par an |
| `annualized_volatility` | std(r, ddof=1) x sqrt(252) (papier) | décimal par an |
| `sharpe_ratio` | (R_ann - R_f) / sigma_ann (papier) | sans unité |
| `rolling_sharpe` | (moyenne(r, w) - R_f,j) / std(r, w) sur w jours (papier) | sans unité |
| `sortino_ratio` | (R_ann - R_f) / (sqrt(moyenne(min(r - R_f,j, 0)^2)) x sqrt(252)) | sans unité |
| `max_drawdown` | min_k (P_k / max_{j<=k} P_j - 1) | décimal, <= 0 |
| `current_drawdown` | P_n / max_j P_j - 1 | décimal, <= 0 |
| `calmar_ratio` | R_ann / abs(perte maximale) | sans unité |

Hypothèses (H) :
* H1 : écart-type d'échantillon (ddof = 1) ; le papier ne précise pas.
* H2 : `rf_annual` est un taux annuel en décimal ; le taux journalier est (1 + R_f)^(1/252) - 1.
  Le papier utilise le Treasury 1 mois ; le choix de la série est celui de l'appelant
  (`tools.market_data`).
* H3 : Sortino : seuil minimal acceptable (MAR) = taux sans risque journalier ; semi-écart calculé
  sur les n rendements (dénominateur n, pas seulement les rendements négatifs).
* H5 : `sharpe_ratio` et `sortino_ratio` lèvent `DegenerateSeriesError` quand la volatilité
  annualisée est inférieure à `MIN_ANNUALIZED_VOLATILITY` = 1e-4 (série quasi plate, p. ex.
  monétaire) : le ratio serait un nombre sans signification. `rolling_sharpe` met une valeur
  ABSENTE (NaN) pour toute fenêtre dont la volatilité annualisée est sous ce seuil.
  `SORTINO_MIN_VOLATILITY` reste un alias de l'ancien nom.
* H6 : `calmar_ratio` lève `DegenerateSeriesError` si |perte maximale| < `MIN_ABS_DRAWDOWN` = 1e-6
  (une perte de l'ordre de 1e-12, bruit flottant, donnerait un ratio absurde).
* H4 : `rolling_sharpe` est exprimé en unités journalières comme dans la formule du papier ;
  `annualize=True` le multiplie par sqrt(252).

Cas limites : fenêtre plus longue que l'historique connu -> `InsufficientDataError` ; NaN dans la
fenêtre -> `MissingDataError` ; volatilité, semi-écart ou perte maximale nuls (ratio non défini) ->
`DegenerateSeriesError`. Jamais de ratio infini ni de valeur de remplacement.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from amundi_agentic.tools.base import (
    TRADING_DAYS,
    DegenerateSeriesError,
    InsufficientDataError,
    ToolResult,
    known_before,
    make_meta,
    sample_std,
    series_label,
    simple_returns,
    trailing_prices,
)

DEFAULT_WINDOW = TRADING_DAYS
# H5 : en dessous de cette volatilité annualisée (1 point de base), le Sortino est refusé : sur un
# monétaire plat avec R_f > 0, le semi-écart est ~ R_f,j et le ratio (~ -16) est défini mais ne veut rien dire.
MIN_ANNUALIZED_VOLATILITY = 1e-4
SORTINO_MIN_VOLATILITY = MIN_ANNUALIZED_VOLATILITY  # alias de l'ancien nom
# H6 : perte maximale minimale (valeur absolue, 0,01 %) pour le Calmar ; en dessous, ratio refusé.
MIN_ABS_DRAWDOWN = 1e-6


def daily_rf(rf_annual: float) -> float:
    """Taux journalier équivalent à un taux annuel : (1 + R_f)^(1/252) - 1 (H2)."""
    if not np.isfinite(rf_annual) or rf_annual <= -1.0:
        raise ValueError("rf_annual doit être un taux annuel décimal fini, supérieur à -1")
    return float((1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0)


def _cum(w: pd.Series) -> float:
    return float(w.iloc[-1] / w.iloc[0] - 1.0)


def _ann(cum: float, n: int) -> float:
    return float((1.0 + cum) ** (TRADING_DAYS / n) - 1.0)


def cumulative_return(
    prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW
) -> ToolResult[float]:
    w = trailing_prices(prices, as_of, window)
    return ToolResult(
        _cum(w),
        make_meta(
            "cumulative_return", as_of, w.index, len(w), window=window, series=series_label(prices)
        ),
    )


def annualized_return(
    prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW
) -> ToolResult[float]:
    """R_annualisé = (1 + R_cumulé)^(252/n) - 1, n = `window`."""
    w = trailing_prices(prices, as_of, window)
    return ToolResult(
        _ann(_cum(w), window),
        make_meta(
            "annualized_return", as_of, w.index, len(w), window=window, series=series_label(prices)
        ),
    )


def annualized_volatility(
    prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW
) -> ToolResult[float]:
    """sigma_annualisée = sigma_quotidienne x sqrt(252) (H1 : ddof = 1)."""
    w = trailing_prices(prices, as_of, window)
    sigma = sample_std(simple_returns(w).to_numpy())
    return ToolResult(
        float(sigma * np.sqrt(TRADING_DAYS)),
        make_meta(
            "annualized_volatility",
            as_of,
            w.index,
            len(w),
            window=window,
            series=series_label(prices),
        ),
    )


def sharpe_ratio(
    prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW, rf_annual: float = 0.0
) -> ToolResult[float]:
    """S = (R_annualisé - R_f) / sigma_annualisée. Volatilité nulle -> erreur."""
    w = trailing_prices(prices, as_of, window)
    sigma = sample_std(simple_returns(w).to_numpy()) * np.sqrt(TRADING_DAYS)
    if sigma < MIN_ANNUALIZED_VOLATILITY:
        raise DegenerateSeriesError(
            f"Sharpe non défini : volatilité annualisée {sigma:.3g} < {MIN_ANNUALIZED_VOLATILITY:g}"
        )
    valeur = (_ann(_cum(w), window) - rf_annual) / sigma
    return ToolResult(
        float(valeur),
        make_meta(
            "sharpe_ratio",
            as_of,
            w.index,
            len(w),
            window=window,
            rf_annual=rf_annual,
            series=series_label(prices),
        ),
    )


def rolling_sharpe(
    prices: pd.Series,
    as_of: date,
    window: int = 63,
    rf_annual: float = 0.0,
    annualize: bool = False,
) -> ToolResult[pd.Series]:
    """Sharpe glissant du papier : (moyenne des rendements sur w jours - R_f,j) / écart-type sur w.

    Une valeur par séance connue (fenêtre arrière uniquement, jamais centrée). Fenêtre incomplète,
    contenant un NaN, ou de volatilité nulle : valeur ABSENTE (NaN), jamais comblée. Fenêtre `w`
    par défaut = 63 séances (H, environ 3 mois).
    """
    if window < 2:
        raise ValueError("fenêtre du Sharpe glissant : au moins 2 rendements")
    connu = known_before(prices, as_of, "prix").astype(float)
    if len(connu) < window + 1:
        raise InsufficientDataError(
            f"Sharpe glissant : {len(connu)} observations, {window + 1} requises"
        )
    p = connu.where(connu > 0)  # un prix <= 0 rend absentes les fenêtres qui le contiennent
    r = p / p.shift(1) - 1.0
    moyenne = r.rolling(window, min_periods=window).mean()
    ecart = r.rolling(window, min_periods=window).std(ddof=1)
    ecart = ecart.where(ecart * np.sqrt(TRADING_DAYS) >= MIN_ANNUALIZED_VOLATILITY)
    s = (moyenne - daily_rf(rf_annual)) / ecart
    if annualize:
        s = s * np.sqrt(TRADING_DAYS)
    s = s.iloc[window:]  # les `window` premiers rendements n'existent qu'à partir de l'index window
    return ToolResult(
        s.rename("rolling_sharpe"),
        make_meta(
            "rolling_sharpe",
            as_of,
            connu.index,
            len(connu),
            window=window,
            rf_annual=rf_annual,
            annualize=annualize,
            series=series_label(prices),
        ),
    )


def sortino_ratio(
    prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW, rf_annual: float = 0.0
) -> ToolResult[float]:
    """Sortino : (R_annualisé - R_f) / semi-écart annualisé (MAR = R_f,j, H3)."""
    w = trailing_prices(prices, as_of, window)
    r = simple_returns(w).to_numpy()
    vol = sample_std(r) * np.sqrt(TRADING_DAYS)
    if vol < MIN_ANNUALIZED_VOLATILITY:
        raise DegenerateSeriesError(
            f"Sortino non défini : volatilité annualisée {vol:.3g} < {MIN_ANNUALIZED_VOLATILITY:g} "
            "(série quasi plate : le ratio ne mesurerait que R_f - rendement divisé par du bruit)"
        )
    manque = np.minimum(r - daily_rf(rf_annual), 0.0)
    dd = float(np.sqrt(np.mean(manque**2)) * np.sqrt(TRADING_DAYS))
    if dd == 0.0:
        raise DegenerateSeriesError("Sortino non défini : aucun rendement sous le seuil (MAR)")
    valeur = (_ann(_cum(w), window) - rf_annual) / dd
    return ToolResult(
        float(valeur),
        make_meta(
            "sortino_ratio",
            as_of,
            w.index,
            len(w),
            window=window,
            rf_annual=rf_annual,
            series=series_label(prices),
        ),
    )


def _mdd(w: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    p = w.to_numpy(dtype=float)
    pic = np.maximum.accumulate(p)
    dd = p / pic - 1.0
    k = int(np.argmin(dd))  # première occurrence du creux le plus profond
    j = int(np.argmax(p[: k + 1]))
    return float(dd[k]), w.index[j], w.index[k]


def max_drawdown(
    prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW
) -> ToolResult[dict[str, object]]:
    """Perte maximale (décimal <= 0) sur la fenêtre, avec dates du pic et du creux."""
    w = trailing_prices(prices, as_of, window)
    valeur, pic, creux = _mdd(w)
    return ToolResult(
        {"max_drawdown": valeur, "peak_date": pic.date(), "trough_date": creux.date()},
        make_meta(
            "max_drawdown", as_of, w.index, len(w), window=window, series=series_label(prices)
        ),
    )


def current_drawdown(
    prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW
) -> ToolResult[float]:
    """Creux courant : dernier prix / plus haut de la fenêtre - 1 (décimal <= 0)."""
    w = trailing_prices(prices, as_of, window)
    return ToolResult(
        float(w.iloc[-1] / w.max() - 1.0),
        make_meta(
            "current_drawdown", as_of, w.index, len(w), window=window, series=series_label(prices)
        ),
    )


def calmar_ratio(prices: pd.Series, as_of: date, window: int = DEFAULT_WINDOW) -> ToolResult[float]:
    """Calmar = R_annualisé / |perte maximale| sur la même fenêtre. Aucune baisse -> erreur."""
    w = trailing_prices(prices, as_of, window)
    mdd, _, _ = _mdd(w)
    if abs(mdd) < MIN_ABS_DRAWDOWN:
        raise DegenerateSeriesError(
            f"Calmar non défini : perte maximale {abs(mdd):.3g} < {MIN_ABS_DRAWDOWN:g}"
        )
    return ToolResult(
        float(_ann(_cum(w), window) / abs(mdd)),
        make_meta(
            "calmar_ratio", as_of, w.index, len(w), window=window, series=series_label(prices)
        ),
    )
