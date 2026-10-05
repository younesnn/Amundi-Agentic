"""Fabriques synthétiques pour les tests de `tools/` (aucun réseau, aucune clé, aucun LLM)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


def serie(values, start: str = "2024-01-02") -> pd.Series:
    """Série de clôtures sur des jours ouvrés consécutifs."""
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series([float(v) for v in values], index=idx, name="px")


def apres(s: pd.Series | pd.DataFrame) -> date:
    """Date t = lendemain calendaire de la dernière barre : toutes les barres sont connues."""
    return (s.index[-1] + pd.Timedelta(days=1)).date()


def depuis_rendements(rendements, p0: float = 100.0, start: str = "2024-01-02") -> pd.Series:
    """Prix dont les rendements simples successifs sont `rendements` (n rendements, n + 1 prix)."""
    prix = [p0]
    for r in rendements:
        prix.append(prix[-1] * (1.0 + r))
    return serie(prix, start)


def marche_aleatoire(n: int = 900, graine: int = 0, start: str = "2018-01-02") -> pd.Series:
    """Marche aléatoire reproductible (graine fixe), prix positifs."""
    rng = np.random.default_rng(graine)
    r = rng.normal(0.0003, 0.01, size=n - 1)
    return depuis_rendements(r, 100.0, start)


def avec_futur(s: pd.Series, as_of: date) -> pd.Series:
    """Ajoute des barres à t (incluse) et après, de valeurs extrêmes ou manquantes."""
    futur_dates = [pd.Timestamp(as_of) + timedelta(days=k) for k in range(0, 6)]
    futur_vals = [1e6, 3.0, np.nan, -5.0, 1e-3, 777.0]
    futur = pd.Series(futur_vals, index=pd.DatetimeIndex(futur_dates), name=s.name)
    return pd.concat([s, futur])
