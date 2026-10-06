# ruff: noqa: E501, N806, N818
"""Mesure de performance APRÈS COUP (D-065) : jamais appelée pendant la production des décisions.

Les formules sont celles du papier, déjà dans `tools/finance.py` (rendement cumulé et annualisé,
volatilité annualisée, Sharpe, Sharpe glissant, perte maximale) : ce module construit seulement la
valeur d'un portefeuille (équipondéré à l'entrée, achat et conservation : UN SEUL rééquilibrage,
aucun coût de transaction) et appelle ces fonctions. Les prix reçus sont déjà servis comme
`as_of(as_of_performance)` par la couche de données ; ce module refuse tout prix après `fin_suivi`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from amundi_agentic.data.models import LookAheadError
from amundi_agentic.tools.base import (
    DegenerateSeriesError,
    InsufficientDataError,
    MissingDataError,
    ToolError,
)
from amundi_agentic.tools.finance import (
    annualized_return,
    annualized_volatility,
    cumulative_return,
    daily_rf,
    max_drawdown,
    rolling_sharpe,
    sharpe_ratio,
)


@dataclass
class Performance:
    cumul: float
    annualise: float
    volatilite: float | None
    sharpe: float | None
    perte_max: float
    pic: str
    creux: str
    n_rendements: int
    rf_annuel: float
    sharpe_glissant: dict[str, float | None] | None = (
        None  # date -> valeur ; jamais affiché sans intervalle
    )
    notes: list[str] = field(default_factory=list)


def fenetre_suivi(prix: pd.DataFrame, t: date, fin: date) -> pd.DataFrame:
    """Clôtures de [t, fin] ; la première ligne est la séance d'entrée. Refuse tout prix > fin."""
    if len(prix) and prix.index.max() > pd.Timestamp(fin):
        raise LookAheadError(
            f"prix postérieurs à fin_suivi={fin} reçus par la mesure de performance"
        )
    return prix.loc[prix.index >= pd.Timestamp(t)]


def geler(prix: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Règle `titre_sans_prix_en_fin_de_suivi` (fixée avant les résultats) : un titre dont les prix
    s'arrêtent avant la fin du suivi (radiation, suspension, absorption) garde sa DERNIÈRE clôture
    connue jusqu'à la fin (position gelée) ; il n'est jamais exclu. Une clôture absente à l'entrée est
    remplacée par la première clôture disponible. Retourne les prix complétés et la liste des cas."""
    cas: dict[str, dict[str, Any]] = {}
    for c in prix.columns:
        s = prix[c]
        dernier, premier = s.last_valid_index(), s.first_valid_index()
        if dernier is None:
            raise MissingDataError(f"{c} : aucune clôture dans le suivi")
        info: dict[str, Any] = {}
        if dernier < prix.index[-1]:
            info["derniere_cloture"] = str(dernier.date())
            info["seances_gelees"] = int((prix.index > dernier).sum())
        if premier > prix.index[0]:
            info["premiere_cloture"] = str(premier.date())
        if info:
            cas[str(c)] = info
    return prix.ffill().bfill(), cas


def taux_quotidiens(taux_pct: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """Taux annuel décimal en vigueur à chaque date : dernière observation connue, reportée (aucune
    interpolation) ; la valeur de la date d utilise l'observation de la veille ou avant (jamais celle
    du jour même : le rendement du jour d n'était pas connu à l'ouverture)."""
    if taux_pct.empty:
        raise MissingDataError("série de taux sans risque vide")
    base = taux_pct.sort_index()
    idx = base.index.union(dates)
    report = base.reindex(idx).ffill().reindex(dates) / 100.0
    decale = report.shift(1)
    decale.iloc[0] = report.iloc[0]  # sans effet : la valeur d'entrée vaut 1 ; évite un NaN inutile
    if decale.isna().any():
        raise MissingDataError("taux sans risque manquant pour une séance du suivi")
    return decale


def taux_moyen(taux_pct: pd.Series, debut: date, fin: date) -> float:
    """Taux sans risque annuel (décimal) moyen sur [début, fin] : le R_f des Sharpe."""
    s = taux_pct.loc[
        (taux_pct.index >= pd.Timestamp(debut)) & (taux_pct.index <= pd.Timestamp(fin))
    ]
    if s.empty:
        raise MissingDataError("aucune observation du taux sans risque dans la fenêtre de suivi")
    return float(s.mean() / 100.0)


def valeur_portefeuille(
    prix: pd.DataFrame, titres: Sequence[str], taux_ann: pd.Series | None = None
) -> pd.Series:
    """Valeur (base 1,0 à l'entrée). Titres : moyenne des prix relatifs (équipondéré à l'entrée, achat
    et conservation). Aucun titre : trésorerie capitalisée au taux sans risque en vigueur (`taux_ann`)."""
    if len(titres):
        sous = prix[list(titres)]
        if sous.isna().any().any():
            raise MissingDataError("clôture manquante dans le suivi d'un titre (aucun remplissage)")
        return (sous / sous.iloc[0]).mean(axis=1).rename("valeur")
    if taux_ann is None:
        raise ValueError("portefeuille vide : le taux sans risque est requis pour la trésorerie")
    quotidien = np.array([1.0] + [1.0 + daily_rf(float(r)) for r in taux_ann.iloc[1:]])
    return pd.Series(np.cumprod(quotidien), index=taux_ann.index, name="valeur")


def mesurer(
    valeur: pd.Series, as_of: date, fin: date, rf_annuel: float, fenetre_glissante: int
) -> Performance:
    """Indicateurs du papier via `tools/finance.py`, sur toute la fenêtre (n rendements = len - 1)."""
    if valeur.index.max() > pd.Timestamp(fin):
        raise LookAheadError("valeur de portefeuille postérieure à fin_suivi")
    n = len(valeur) - 1
    if n < 2:
        raise InsufficientDataError("moins de 2 rendements dans le suivi")
    notes: list[str] = []
    cum = cumulative_return(valeur, as_of, n).value
    ann = annualized_return(valeur, as_of, n).value
    vol: float | None = annualized_volatility(valeur, as_of, n).value
    try:
        sh: float | None = sharpe_ratio(valeur, as_of, n, rf_annual=rf_annuel).value
    except DegenerateSeriesError as exc:
        sh = None
        notes.append(f"Sharpe non défini : {str(exc)[:120]}")
    mdd = max_drawdown(valeur, as_of, n).value
    glissant: dict[str, float | None] | None
    try:
        s = rolling_sharpe(
            valeur, as_of, window=min(fenetre_glissante, n - 1), rf_annual=rf_annuel
        ).value
        glissant = {str(i.date()): (None if pd.isna(x) else float(x)) for i, x in s.items()}
    except (InsufficientDataError, ToolError, ValueError) as exc:
        glissant = None
        notes.append(f"Sharpe glissant non calculé : {str(exc)[:120]}")
    return Performance(
        cumul=float(cum),
        annualise=float(ann),
        volatilite=None if vol is None else float(vol),
        sharpe=None if sh is None else float(sh),
        perte_max=float(mdd["max_drawdown"]),
        pic=str(mdd["peak_date"]),
        creux=str(mdd["trough_date"]),
        n_rendements=n,
        rf_annuel=rf_annuel,
        sharpe_glissant=glissant,
        notes=notes,
    )


def rendements(valeur: pd.Series) -> np.ndarray:
    """Rendements quotidiens simples de la valeur du portefeuille."""
    v = valeur.to_numpy(dtype=float)
    return v[1:] / v[:-1] - 1.0


def prix_relatifs(prix: pd.DataFrame, titres: Sequence[str]) -> np.ndarray:
    """P_fin / P_entrée de chaque titre."""
    sous = prix[list(titres)]
    return (sous.iloc[-1] / sous.iloc[0]).to_numpy(dtype=float)
