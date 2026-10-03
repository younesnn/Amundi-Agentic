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

from dataclasses import dataclass, field
from datetime import date, datetime
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
        }


@dataclass(frozen=True)
class ToolResult(Generic[T]):
    """Valeur calculée + métadonnées de citation."""

    value: T
    meta: ToolMeta


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
    **params: Any,
) -> ToolMeta:
    debut = fin = None
    if index is not None and len(index):
        debut = pd.Timestamp(index.min()).date()
        fin = pd.Timestamp(index.max()).date()
    return ToolMeta(tool, TOOL_VERSION, as_of, debut, fin, n_obs, params)
