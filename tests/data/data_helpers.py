"""Fabriques de données synthétiques partagées par les tests de `data/`."""

from __future__ import annotations

import pandas as pd


def prix(dates, closes, dividends=None, splits=None) -> pd.DataFrame:
    n = len(dates)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": [float(c) for c in closes],
            "volume": [1000.0] * n,
            "dividends": dividends or [0.0] * n,
            "splits": splits or [0.0] * n,
        }
    )


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")
