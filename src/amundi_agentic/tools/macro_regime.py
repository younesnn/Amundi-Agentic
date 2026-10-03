# ruff: noqa: E501
"""Macro : indicateurs de régime calculés en Python à partir des séries FRED et BCE (L1 §4).

Entrée : pour chaque série, un tableau au format de `DataView.macro_long` (colonnes `date`, `value`,
`available_from`). L'outil réapplique lui-même la règle de disponibilité (`available_from` < t ET
`date` < t, `base.known_macro`) : un millésime publié après t, ou une observation sans date de
publication connue avant t, n'est jamais lu. Toutes les comparaisons se font en ARRIÈRE depuis la
dernière observation connue (aucune fenêtre centrée, aucune interpolation, aucun remplissage vers
l'avant ni vers l'arrière).

| Indicateur | Définition | Unité |
| --- | --- | --- |
| `croissance_pib_yoy` | GDPC1(dernier) / GDPC1(1 an avant) - 1 | décimal |
| `inflation_ipc_yoy` | CPIAUCSL(dernier) / CPIAUCSL(1 an avant) - 1 | décimal |
| `chomage`, `chomage_var_12m` | UNRATE / 100 ; différence avec 12 mois avant | décimal (points de % / 100) |
| `taux_10y`, `taux_2y` | DGS10 / 100, DGS2 / 100 ; `taux_10y_var_3m`, `_12m` : différences | décimal |
| `pente_us_10y_2y` (+ `_var_3m`, `_var_12m`) | T10Y2Y / 100 ; à défaut DGS10 - DGS2 à la même date | décimal |
| `pente_euro_10y_2y` (+ variations) | YC_SPOT_10Y - YC_SPOT_2Y à la même date, / 100 | décimal |
| `ecart_credit_hy` (+ `_var_3m`) | BAMLH0A0HYM2 / 100 | décimal |
| `vix`, `vix_var_3m` | VIXCLS ; différence | points d'indice |
| `estr` | ESTR / 100 | décimal |
| `quadrant` | croissance_pib_yoy >= seuil ? haute : basse ; inflation_ipc_yoy >= seuil ? haute : basse | étiquette |

Quadrants (H) : `expansion_desinflation` (croissance haute, inflation basse), `surchauffe`
(haute, haute), `stagflation` (basse, haute), `ralentissement` (basse, basse).

Hypothèses (H) :
* H1 : seuils du quadrant = 2 % pour la croissance annuelle du PIB réel et 2 % pour l'inflation
  annuelle (cible de la Fed et de la BCE ; ordre de grandeur de la croissance potentielle). L1 ne
  fixe aucun seuil : paramètres de `MacroThresholds`, à geler dans la configuration.
* H2 : un indicateur n'est calculé que si la dernière observation connue a au plus `max_age_days`
  jours à t (série quotidienne 10 j, mensuelle 100 j, trimestrielle 220 j) ; sinon il est ABSENT.
* H3 : « il y a k mois / 1 an » = dernière observation de date <= (dernière date - k mois) et au
  plus `lookback_tolerance_days` plus ancienne (7 j quotidien ; 10 j mensuel ou trimestriel) ;
  sinon la variation est ABSENTE. Le PIB et le CPI sont lus au millésime connu à t pour chaque
  observation (révisions antérieures à t incluses, révisions postérieures exclues).
* H4 : variation d'un taux ou d'un écart = différence de niveaux en décimal (pas de variation relative).

Règle des données manquantes : série absente, vide, trop ancienne ou sans point de comparaison ->
l'indicateur est absent de `indicateurs`, sa raison est dans `manquants` ; si la croissance ou
l'inflation manque, `quadrant` vaut None. Aucune valeur de remplacement.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from amundi_agentic.tools.base import (
    MissingDataError,
    ToolError,
    ToolResult,
    check_as_of,
    known_macro,
    make_meta,
)

DEFAULT_IDS: dict[str, str] = {
    "pib": "fred:GDPC1",
    "ipc": "fred:CPIAUCSL",
    "chomage": "fred:UNRATE",
    "taux_10y": "fred:DGS10",
    "taux_2y": "fred:DGS2",
    "pente_us": "fred:T10Y2Y",
    "credit_hy": "fred:BAMLH0A0HYM2",
    "vix": "fred:VIXCLS",
    "euro_10y": "ecb:YC_SPOT_10Y",
    "euro_2y": "ecb:YC_SPOT_2Y",
    "estr": "ecb:ESTR",
}
FREQUENCY: dict[str, str] = {
    "pib": "trimestriel",
    "ipc": "mensuel",
    "chomage": "mensuel",
    "taux_10y": "quotidien",
    "taux_2y": "quotidien",
    "pente_us": "quotidien",
    "credit_hy": "quotidien",
    "vix": "quotidien",
    "euro_10y": "quotidien",
    "euro_2y": "quotidien",
    "estr": "quotidien",
}


@dataclass(frozen=True)
class MacroThresholds:
    growth_yoy: float = 0.02  # H1
    inflation_yoy: float = 0.02  # H1
    max_age_days: Mapping[str, int] = field(
        default_factory=lambda: {"quotidien": 10, "mensuel": 100, "trimestriel": 220}
    )  # H2
    lookback_tolerance_days: Mapping[str, int] = field(
        default_factory=lambda: {"quotidien": 7, "mensuel": 10, "trimestriel": 10}
    )  # H3

    def to_dict(self) -> dict[str, Any]:
        return {k: (dict(v) if isinstance(v, Mapping) else v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class MacroRegime:
    indicateurs: dict[str, float]
    dates: dict[str, date]  # date de la dernière observation utilisée, par indicateur
    drapeaux: dict[str, bool]
    manquants: dict[str, str]
    quadrant: str | None
    seuils: dict[str, Any]


def _at_or_before(
    df: pd.DataFrame, cible: pd.Timestamp, tol_days: int
) -> tuple[pd.Timestamp, float]:
    d = df[df["date"] <= cible]
    if d.empty:
        raise MissingDataError(f"aucune observation à {cible.date()} ou avant")
    dt = d["date"].iloc[-1]
    if (cible - dt).days > tol_days:
        raise MissingDataError(
            f"observation la plus proche de {cible.date()} trop ancienne ({dt.date()})"
        )
    return dt, float(d["value"].iloc[-1])


class _Ctx:
    def __init__(
        self,
        series: Mapping[str, pd.DataFrame],
        ids: Mapping[str, str],
        as_of: date,
        th: MacroThresholds,
    ) -> None:
        self.series, self.ids, self.as_of, self.th = series, ids, as_of, th
        self.t = check_as_of(as_of)
        self.ind: dict[str, float] = {}
        self.dates: dict[str, date] = {}
        self.miss: dict[str, str] = {}
        self.used: list[pd.Timestamp] = []

    def frame(self, role: str) -> pd.DataFrame:
        sid = self.ids[role]
        if sid not in self.series:
            raise MissingDataError(f"série {sid} absente des entrées")
        k = known_macro(self.series[sid], self.as_of, sid)
        if k.empty:
            raise MissingDataError(f"série {sid} : aucune observation connue à t")
        age = (self.t - k["date"].iloc[-1]).days
        maxi = self.th.max_age_days[FREQUENCY[role]]
        if age > maxi:
            raise MissingDataError(
                f"série {sid} : dernière observation connue {k['date'].iloc[-1].date()} "
                f"({age} j, maximum {maxi} j)"
            )
        return k

    def derived_slope(self, hi: str, lo: str) -> pd.DataFrame:
        a, b = self.frame(hi), self.frame(lo)
        m = a.merge(b, on="date", suffixes=("_hi", "_lo"))
        if a["date"].iloc[-1] != b["date"].iloc[-1] or m.empty:
            raise MissingDataError("pente : dernières observations des deux taux non alignées")
        return pd.DataFrame({"date": m["date"], "value": m["value_hi"] - m["value_lo"]})

    def record(self, name: str, df: pd.DataFrame, value: float, scale: float = 1.0) -> None:
        self.ind[name] = value / scale
        self.dates[name] = df["date"].iloc[-1].date()
        self.used.append(df["date"].iloc[-1])

    def tol(self, role: str) -> int:
        return self.th.lookback_tolerance_days[FREQUENCY[role]]

    def attempt(self, name: str, f) -> None:
        try:
            f()
        except ToolError as e:
            self.miss[name] = str(e)

    def level_and_changes(
        self,
        name: str,
        role: str,
        months: tuple[int, ...],
        scale: float,
        df: pd.DataFrame | None = None,
    ) -> None:
        def niveau() -> pd.DataFrame:
            d = df if df is not None else self.frame(role)
            self.record(name, d, float(d["value"].iloc[-1]), scale)
            return d

        try:
            d = niveau()
        except ToolError as e:
            self.miss[name] = str(e)
            for m in months:
                self.miss[f"{name}_var_{m}m"] = "niveau indisponible"
            return
        dernier = d["date"].iloc[-1]
        for m in months:
            nm = f"{name}_var_{m}m"
            try:
                dt, v0 = _at_or_before(d, dernier - pd.DateOffset(months=m), self.tol(role))
                self.ind[nm] = (float(d["value"].iloc[-1]) - v0) / scale
                self.dates[nm] = dernier.date()
                self.used.append(dt)
            except ToolError as e:
                self.miss[nm] = str(e)

    def yoy(self, name: str, role: str) -> None:
        d = self.frame(role)
        dernier = d["date"].iloc[-1]
        dt, v0 = _at_or_before(d, dernier - pd.DateOffset(years=1), self.tol(role))
        if v0 <= 0:
            raise MissingDataError(f"{self.ids[role]} : niveau de référence non positif")
        self.record(name, d, float(d["value"].iloc[-1]) / v0 - 1.0)
        self.used.append(dt)


def macro_regime(
    series: Mapping[str, pd.DataFrame],
    as_of: date,
    thresholds: MacroThresholds | None = None,
    ids: Mapping[str, str] | None = None,
) -> ToolResult[MacroRegime]:
    """Indicateurs de régime macro à t ; voir la docstring du module pour formules et règles."""
    th = thresholds or MacroThresholds()
    idm = {**DEFAULT_IDS, **(ids or {})}
    c = _Ctx(series, idm, as_of, th)

    c.attempt("croissance_pib_yoy", lambda: c.yoy("croissance_pib_yoy", "pib"))
    c.attempt("inflation_ipc_yoy", lambda: c.yoy("inflation_ipc_yoy", "ipc"))
    c.level_and_changes("chomage", "chomage", (12,), 100.0)
    c.level_and_changes("taux_10y", "taux_10y", (3, 12), 100.0)
    c.level_and_changes("taux_2y", "taux_2y", (3, 12), 100.0)
    # pente US : T10Y2Y, à défaut DGS10 - DGS2 (même date)
    try:
        pente = c.frame("pente_us")
    except ToolError:
        try:
            pente = c.derived_slope("taux_10y", "taux_2y")
        except ToolError as e:
            pente = None
            c.miss["pente_us_10y_2y"] = str(e)
    if pente is not None:
        c.level_and_changes("pente_us_10y_2y", "pente_us", (3, 12), 100.0, df=pente)
    try:
        c.level_and_changes(
            "pente_euro_10y_2y",
            "euro_10y",
            (3, 12),
            100.0,
            df=c.derived_slope("euro_10y", "euro_2y"),
        )
    except ToolError as e:
        c.miss["pente_euro_10y_2y"] = str(e)
    c.level_and_changes("ecart_credit_hy", "credit_hy", (3,), 100.0)
    c.level_and_changes("vix", "vix", (3,), 1.0)
    c.level_and_changes("estr", "estr", (), 100.0)

    drapeaux: dict[str, bool] = {}
    for nom in ("pente_us_10y_2y", "pente_euro_10y_2y"):
        if nom in c.ind:
            drapeaux[f"courbe_inversee_{nom.split('_')[1]}"] = c.ind[nom] < 0

    quadrant = None
    if "croissance_pib_yoy" in c.ind and "inflation_ipc_yoy" in c.ind:
        g = c.ind["croissance_pib_yoy"] >= th.growth_yoy
        p = c.ind["inflation_ipc_yoy"] >= th.inflation_yoy
        quadrant = {
            (True, False): "expansion_desinflation",
            (True, True): "surchauffe",
            (False, True): "stagflation",
            (False, False): "ralentissement",
        }[(g, p)]
    else:
        c.miss["quadrant"] = "croissance ou inflation indisponible"

    return ToolResult(
        MacroRegime(c.ind, c.dates, drapeaux, c.miss, quadrant, th.to_dict()),
        make_meta(
            "macro_regime",
            as_of,
            pd.DatetimeIndex(c.used) if c.used else None,
            len(c.ind),
            ids=dict(idm),
        ),
    )
