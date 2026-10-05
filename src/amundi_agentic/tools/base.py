"""Briques communes des outils de calcul : erreurs explicites, métadonnées de citation, fenêtres.

Principes (L1 §4, §5, §11.3 ; D-031, D-038 ; EX-O1-03, EX-O1-04) :

* un outil est une fonction pure et déterministe : mêmes entrées, même sortie, aucune lecture
  d'horloge, de fichier, de réseau ni de LLM ;
* `as_of` (la date t) est un argument obligatoire. Un prix n'est utilisé que si sa date de séance
  est STRICTEMENT antérieure à t (D-038) : une série qui contiendrait des barres de t ou après
  est tronquée par l'outil lui-même, jamais lue (garantie de non-fuite indépendante de l'appelant) ;
* aucun remplissage : une série trop courte, une valeur manquante dans la fenêtre ou une volatilité
  nulle lèvent une erreur explicite (sous-classe de `ToolError`) ; il n'y a jamais de nombre
  inventé ni de valeur par défaut silencieuse ;
* les rendements sont en décimal (0,05 = 5 %), les dates sont des `datetime.date`.

Chaque sortie est un `ToolResult` : la valeur et un `ToolMeta` (nom de l'outil, version, t, fenêtre,
dernière date utilisée) qui permet de construire une `Source` citable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Generic, TypeVar

import numpy as np
import pandas as pd

TOOL_VERSION = "1.0.0"
TRADING_DAYS = 252  # papier AlphaAgents : 252 séances par an
WEEKS_PER_YEAR = 52

T = TypeVar("T")


class ToolError(ValueError):
    """Erreur explicite d'un outil : l'agent ne reçoit jamais de chiffre de remplacement."""


class InsufficientDataError(ToolError):
    """Historique trop court pour la fenêtre demandée."""


class MissingDataError(ToolError):
    """Valeur manquante (NaN) ou entrée absente dans la fenêtre : aucun remplissage n'est fait."""


class DegenerateSeriesError(ToolError):
    """Quantité non définie sur cette série (volatilité nulle, aucune baisse, prix non positif)."""


_SAFE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")


def _escape_series(nom: str) -> str:
    return "".join(c if c in _SAFE else "".join(f"%{b:02X}" for b in c.encode()) for c in nom)


def _norm(v: Any) -> Any:
    """Valeur normalisée, sérialisable en JSON, indépendante du type numpy ou python d'origine."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool | np.bool_):
        return bool(v)
    if isinstance(v, int | np.integer):
        return int(v)
    if isinstance(v, float | np.floating):
        f = float(v)
        if f != f:
            return {"__float__": "nan"}
        if f in (float("inf"), float("-inf")):
            return {"__float__": "inf" if f > 0 else "-inf"}
        return f
    if isinstance(v, pd.Timestamp | datetime | date):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}
    if isinstance(v, list | tuple | np.ndarray | pd.Index):
        return [_norm(x) for x in list(v)]
    if isinstance(v, set | frozenset):
        return sorted((_norm(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
    return str(v)


def canonical_params(params: dict[str, Any]) -> str:
    """JSON canonique (clés triées, séparateurs fixes, ASCII) des paramètres normalisés."""
    return json.dumps(_norm(params), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class ToolMeta:
    """Métadonnées pour citer la sortie d'un outil (EX-O1-03)."""

    tool: str
    version: str
    as_of: date
    window_start: date | None
    last_data_date: date | None
    n_obs: int
    params: dict[str, Any] = field(default_factory=dict)
    series: str | None = None  # série (ou actif) sur laquelle porte le calcul, si elle est nommée
    unit: str | None = None  # unité de la valeur (« décimal », « décimal par an », « sans unité »…)

    @property
    def source_id(self) -> str:
        """Identifiant stable et déterministe : outil, série, fenêtre, version + empreinte des
        paramètres (deux appels de mêmes dates mais de paramètres différents, p. ex. un autre
        taux sans risque, n'ont pas le même identifiant). Aucune horloge, aucun aléa.

        Nom de série : chaque caractère hors [A-Za-z0-9_.-] (dont « : », « # », l'espace et « % »)
        est remplacé par %XX sur ses octets UTF-8 : codage injectif, donc identifiant non ambigu ;
        l'absence de série s'écrit « ~ » (jamais produit par le codage, « ~ » est lui-même
        échappé). Empreinte : sha256 (8 premiers hex) du JSON canonique des paramètres normalisés
        (`canonical_params`), identique entre processus et versions de numpy."""
        debut = self.window_start.isoformat() if self.window_start else "na"
        fin = self.last_data_date.isoformat() if self.last_data_date else "na"
        empreinte = hashlib.sha256(canonical_params(self.params).encode()).hexdigest()[:8]
        serie = "~" if self.series is None else _escape_series(self.series)
        return f"{self.tool}:{serie}:{debut}:{fin}:v{self.version}#{empreinte}"

    @property
    def data_instant(self) -> datetime | None:
        """Instant UTC AWARE de la dernière donnée utilisée : minuit UTC de sa date (la date de
        séance ou d'observation n'a pas d'heure ; ce choix est sans effet sur la coupure PIT, qui
        est faite en amont). None si aucune donnée n'a été utilisée."""
        if self.last_data_date is None:
            return None
        d = self.last_data_date
        return datetime(d.year, d.month, d.day, tzinfo=UTC)

    def citation(self) -> str:
        debut = self.window_start.isoformat() if self.window_start else "n/a"
        fin = self.last_data_date.isoformat() if self.last_data_date else "n/a"
        return (
            f"{self.tool}@{self.version} ; t={self.as_of.isoformat()} ; "
            f"fenêtre {debut} à {fin} ({self.n_obs} obs.)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "version": self.version,
            "as_of": self.as_of.isoformat(),
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "last_data_date": self.last_data_date.isoformat() if self.last_data_date else None,
            "n_obs": self.n_obs,
            "params": dict(self.params),
            "series": self.series,
            "unit": self.unit,
            "source_id": self.source_id,
        }


@dataclass(frozen=True)
class ToolResult(Generic[T]):
    """Valeur calculée + métadonnées de citation."""

    value: T
    meta: ToolMeta

    @property
    def extrait(self) -> str:
        """Résumé lisible du calcul (outil, fenêtre, valeur, unité), 500 caractères au plus.

        Destiné au champ `extrait` d'une `Source` (L1 §5.3) ; les agents font la correspondance,
        `tools/` n'importe pas `schemas.py`.
        """
        unite = f" {self.meta.unit}" if self.meta.unit else ""
        texte = f"{self.meta.citation()} ; valeur = {_resume(self.value)}{unite}"
        return texte if len(texte) <= EXTRAIT_MAX else texte[: EXTRAIT_MAX - 1] + "…"


EXTRAIT_MAX = 500


def _resume(v: Any) -> str:
    """Résumé court et déterministe d'une valeur d'outil (nombres en 6 chiffres significatifs)."""
    if isinstance(v, float | np.floating):
        return f"{float(v):.6g}"
    if isinstance(v, pd.Series):
        return f"série de {len(v)} valeurs, dernière = {_resume(v.iloc[-1]) if len(v) else 'n/a'}"
    if isinstance(v, pd.DataFrame):
        return f"tableau {v.shape[0]} x {v.shape[1]}"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_resume(x)}" for k, x in list(v.items())[:12]) + "}"
    if hasattr(v, "__dataclass_fields__"):
        return _resume({k: getattr(v, k) for k in v.__dataclass_fields__})
    if isinstance(v, list | tuple):
        return "[" + ", ".join(_resume(x) for x in v[:12]) + "]"
    return str(v)


def series_label(s: Any) -> str | None:
    """Nom de la série d'entrée s'il existe (pour citer la source), sinon None."""
    nom = getattr(s, "name", None)
    return None if nom is None else str(nom)


# Unité de la valeur de chaque outil (documentation de la sortie, jamais utilisée pour calculer)
UNITS: dict[str, str] = {
    "cumulative_return": "décimal",
    "annualized_return": "décimal par an",
    "annualized_volatility": "décimal par an",
    "sharpe_ratio": "sans unité",
    "rolling_sharpe": "sans unité (journalier sauf annualize)",
    "sortino_ratio": "sans unité",
    "max_drawdown": "décimal (<= 0)",
    "current_drawdown": "décimal (<= 0)",
    "calmar_ratio": "sans unité",
    "momentum": "décimal",
    "momentum_12_1": "décimal",
    "trend_vs_sma": "décimal (écart à la moyenne mobile)",
    "valuation_summary": "décimal (voir clés)",
    "realized_volatility": "décimal par an",
    "ewma_volatility": "décimal par an",
    "historical_var": "perte, décimal",
    "historical_cvar": "perte, décimal",
    "correlation_matrix": "corrélation [-1, 1]",
    "volatility_regime": "régime (normal/haut) et volatilité en décimal par an",
    "risk_report": "alertes (aucune/moderee/elevee)",
    "macro_regime": "décimal (taux en décimal, VIX en points)",
    "risk_free_annual": "décimal par an",
}


def check_as_of(as_of: date) -> pd.Timestamp:
    if isinstance(as_of, datetime) or not isinstance(as_of, date):
        raise TypeError("as_of doit être une date (datetime.date), pas un datetime")
    return pd.Timestamp(as_of)


def _check_index(s: pd.Series | pd.DataFrame, name: str) -> None:
    if not isinstance(s.index, pd.DatetimeIndex):
        raise ToolError(f"{name} : l'index doit être un DatetimeIndex")
    if s.index.tz is not None:
        raise ToolError(f"{name} : index daté sans fuseau attendu (dates de séance)")
    if not s.index.is_monotonic_increasing or not s.index.is_unique:
        raise ToolError(f"{name} : index non trié ou en double")


def known_before(s: pd.Series | pd.DataFrame, as_of: date, name: str = "série"):
    """Observations dont la date est STRICTEMENT antérieure à t (D-038). Renvoie une copie."""
    t = check_as_of(as_of)
    _check_index(s, name)
    return s[s.index < t].copy()


def trailing_prices(
    prices: pd.Series, as_of: date, n_returns: int, name: str = "prix"
) -> pd.Series:
    """Les `n_returns` + 1 derniers prix connus avant t, sans NaN, strictement positifs."""
    if n_returns < 1:
        raise ValueError("la fenêtre doit contenir au moins 1 rendement")
    connu = known_before(prices, as_of, name)
    if len(connu) < n_returns + 1:
        raise InsufficientDataError(
            f"{name} : {len(connu)} observations avant {as_of}, {n_returns + 1} requises"
        )
    fen = connu.iloc[-(n_returns + 1) :].astype(float)
    if fen.isna().any():
        raise MissingDataError(f"{name} : valeur manquante dans la fenêtre (aucun remplissage)")
    if (fen <= 0).any():
        raise DegenerateSeriesError(f"{name} : prix non strictement positif dans la fenêtre")
    return fen


def simple_returns(window_prices: pd.Series) -> pd.Series:
    """Rendements simples P_k / P_{k-1} - 1 (décimal) d'une fenêtre de prix."""
    p = window_prices.to_numpy(dtype=float)
    return pd.Series(p[1:] / p[:-1] - 1.0, index=window_prices.index[1:])


def sample_std(x: np.ndarray) -> float:
    """Écart-type d'échantillon (ddof = 1) ; au moins 2 valeurs."""
    if len(x) < 2:
        raise InsufficientDataError("écart-type : au moins 2 rendements requis")
    return float(np.std(x, ddof=1))


def known_macro(long: pd.DataFrame, as_of: date, name: str = "macro") -> pd.DataFrame:
    """Observations macro connues à t : date < t ET disponibilité (`available_from`) < t.

    `long` suit le format de `DataView.macro_long` : colonnes `date`, `value`, `available_from`.
    La disponibilité est la date de publication (millésime ALFRED, délai déclaré) ; la date de
    l'observation seule ne suffit pas (le PIB d'un trimestre est publié après sa fin). Les valeurs
    NaN sont écartées (pas de remplissage). Résultat trié par date, une ligne par date.
    """
    t = check_as_of(as_of)
    manque = {"date", "value", "available_from"} - set(long.columns)
    if manque:
        raise ToolError(f"{name} : colonnes absentes {sorted(manque)}")
    d = long[(long["date"] < t) & (long["available_from"] < t)].dropna(subset=["value"])
    d = d.sort_values(["date", "available_from"]).drop_duplicates("date", keep="last")
    return d.reset_index(drop=True)


def make_meta(
    tool: str,
    as_of: date,
    index: pd.Index | None,
    n_obs: int,
    *,
    series: str | None = None,
    unit: str | None = None,
    **params: Any,
) -> ToolMeta:
    debut = fin = None
    if index is not None and len(index):
        debut = pd.Timestamp(index.min()).date()
        fin = pd.Timestamp(index.max()).date()
    return ToolMeta(
        tool, TOOL_VERSION, as_of, debut, fin, n_obs, params, series, unit or UNITS.get(tool)
    )
