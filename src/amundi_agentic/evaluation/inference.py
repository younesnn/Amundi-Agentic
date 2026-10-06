# ruff: noqa: E501, N806, N818
"""Inférence de la réplication (D-065 §9) : numpy seulement, graines fixées.

* bootstrap stationnaire par blocs (Politis et Romano, 1994) ;
* distribution exacte des portefeuilles aléatoires de taille m (énumération de C(n, m)), ou
  échantillon seulement si C est trop grand ;
* intervalle de Wilson pour une fréquence ; kappa de Cohen entre deux séries de décisions.

Rien ici ne lit de donnée de marché : les fonctions reçoivent des tableaux.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from statistics import NormalDist

import numpy as np

from amundi_agentic.tools.base import TRADING_DAYS
from amundi_agentic.tools.finance import MIN_ANNUALIZED_VOLATILITY


# ------------------------------------------------------------------------------- Wilson, kappa
def wilson(k: int, n: int, niveau: float = 0.95) -> tuple[float, float] | None:
    """Intervalle de Wilson d'une proportion k/n ; None si n = 0 (rien à mesurer)."""
    if n <= 0:
        return None
    if not 0 <= k <= n:
        raise ValueError("k doit être compris entre 0 et n")
    z = NormalDist().inv_cdf(0.5 + niveau / 2)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    demi = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - demi), min(1.0, centre + demi)


def kappa_cohen(a: Sequence[Hashable], b: Sequence[Hashable]) -> float | None:
    """Kappa de Cohen entre deux séries d'étiquettes. None si non défini (aucun élément, ou accord
    attendu égal à 1 : une seule catégorie utilisée par les deux séries)."""
    if len(a) != len(b):
        raise ValueError("séries de longueurs différentes")
    n = len(a)
    if n == 0:
        return None
    cats = sorted({*a, *b}, key=str)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((sum(x == c for x in a) / n) * (sum(y == c for y in b) / n) for c in cats)
    if math.isclose(pe, 1.0):
        return None
    return (po - pe) / (1 - pe)


# ------------------------------------------------------------------------------- bootstrap
def indices_bootstrap_stationnaire(
    n_obs: int, n_rep: int, longueur_moyenne: float, rng: np.random.Generator
) -> np.ndarray:
    """Indices (n_rep, n_obs) du bootstrap stationnaire : un bloc continue avec la probabilité
    1 - 1/L, sinon un nouvel indice de départ uniforme ; l'index boucle sur la série (circulaire)."""
    if n_obs < 1:
        raise ValueError("série vide")
    p = 1.0 / longueur_moyenne
    idx = np.empty((n_rep, n_obs), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n_obs, n_rep)
    saut = rng.random((n_rep, n_obs)) < p
    departs = rng.integers(0, n_obs, (n_rep, n_obs))
    for k in range(1, n_obs):
        idx[:, k] = np.where(saut[:, k], departs[:, k], (idx[:, k - 1] + 1) % n_obs)
    return idx


@lru_cache(maxsize=4)
def indices_cachees(n_obs: int, n_rep: int, longueur_moyenne: float, graine: int) -> np.ndarray:
    """Mêmes indices pour tous les portefeuilles d'une même longueur (nombres aléatoires communs :
    les différences appariées gardent leur corrélation, et le calcul est fait une seule fois)."""
    rng = np.random.default_rng(_graine_locale(graine, "bootstrap"))
    idx = indices_bootstrap_stationnaire(n_obs, n_rep, longueur_moyenne, rng)
    idx.setflags(write=False)
    return idx


def _cum(r: np.ndarray) -> np.ndarray:
    """Rendement cumulé d'un tableau de rendements quotidiens (dernier axe)."""
    return np.prod(1.0 + r, axis=-1) - 1.0


@dataclass(frozen=True)
class IntervalleDiff:
    estimation: float
    bas: float
    haut: float
    contient_zero: bool
    n_rep: int


def _graine_locale(graine: int, cle: str) -> int:
    import hashlib

    return int(hashlib.sha256(f"{graine}|{cle}".encode()).hexdigest()[:12], 16)


def bootstrap_difference_cumulee(
    ra: np.ndarray,
    rb: np.ndarray,
    *,
    longueur_moyenne: float,
    n_rep: int,
    graine: int,
    niveau: float,
    cle: str = "",
) -> IntervalleDiff:
    """Intervalle (percentiles) de la différence de rendement cumulé entre deux portefeuilles, par
    bootstrap stationnaire des JOURS appariés (les deux séries sont rééchantillonnées avec les
    mêmes indices : la corrélation entre portefeuilles est conservée)."""
    ra, rb = np.asarray(ra, dtype=float), np.asarray(rb, dtype=float)
    if ra.shape != rb.shape or ra.ndim != 1:
        raise ValueError("rendements de même longueur exigés")
    idx = indices_cachees(len(ra), n_rep, longueur_moyenne, graine)
    diffs = _cum(ra[idx]) - _cum(rb[idx])
    a = (1 - niveau) / 2
    bas, haut = (float(x) for x in np.quantile(diffs, [a, 1 - a]))
    est = float(_cum(ra) - _cum(rb))
    return IntervalleDiff(est, bas, haut, bas <= 0.0 <= haut, n_rep)


def sharpe_depuis_rendements(r: np.ndarray, rf_annuel: float) -> np.ndarray | float:
    """Sharpe du papier sur un (ou plusieurs, axe 0) tableau(x) de rendements quotidiens : même
    formule que `tools.finance.sharpe_ratio` ((R_ann - R_f) / sigma_ann, ddof = 1). NaN si la
    volatilité annualisée est sous le seuil de `tools.finance` (série quasi plate)."""
    r = np.asarray(r, dtype=float)
    n = r.shape[-1]
    cum = np.prod(1.0 + r, axis=-1) - 1.0
    ann = (1.0 + cum) ** (TRADING_DAYS / n) - 1.0
    sig = np.std(r, axis=-1, ddof=1) * math.sqrt(TRADING_DAYS)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (ann - rf_annuel) / sig
    return (
        np.where(sig < MIN_ANNUALIZED_VOLATILITY, np.nan, s)
        if np.ndim(s)
        else (float("nan") if sig < MIN_ANNUALIZED_VOLATILITY else float(s))
    )


def bootstrap_sharpe(
    r: np.ndarray,
    rf_annuel: float,
    *,
    longueur_moyenne: float,
    n_rep: int,
    graine: int,
    niveau: float,
    cle: str = "",
) -> tuple[float, float] | None:
    """Intervalle (percentiles) du Sharpe d'un portefeuille, bootstrap stationnaire ; None si le
    Sharpe n'est pas défini sur l'échantillon (série quasi plate : trésorerie)."""
    r = np.asarray(r, dtype=float)
    idx = indices_cachees(len(r), n_rep, longueur_moyenne, graine)
    s = np.asarray(sharpe_depuis_rendements(r[idx], rf_annuel))
    s = s[np.isfinite(s)]
    if len(s) < max(10, n_rep // 2):
        return None
    a = (1 - niveau) / 2
    bas, haut = (float(x) for x in np.quantile(s, [a, 1 - a]))
    return bas, haut


# ------------------------------------------------------------------------------- aléatoire exact
@dataclass(frozen=True)
class DistributionAleatoire:
    m: int
    n: int
    n_combinaisons: int
    exacte: bool
    n_evalues: int
    moyenne: float
    p05: float
    mediane: float
    p95: float
    p_superieur_ou_egal: (
        float | None
    )  # P(portefeuille aléatoire >= observé) ; None sans observation
    percentile_observe: float | None  # part des portefeuilles aléatoires strictement inférieurs


def distribution_aleatoire(
    relatifs: np.ndarray,
    m: int,
    *,
    observe: float | None,
    max_exact: int,
    n_echantillon: int,
    graine: int,
    cle: str = "",
) -> DistributionAleatoire:
    """Distribution du rendement cumulé d'un portefeuille équipondéré (achat et conservation) de m
    titres tirés parmi n. `relatifs` : P_fin / P_entrée de chaque titre (n,). Rendement du portefeuille
    = moyenne(relatifs[S]) - 1. Exact par énumération si C(n, m) <= max_exact, sinon échantillon."""
    rel = np.asarray(relatifs, dtype=float)
    n = len(rel)
    if not 1 <= m <= n:
        raise ValueError("m doit être compris entre 1 et n")
    total = math.comb(n, m)
    if total <= max_exact:
        sous = np.array(list(combinations(range(n), m)), dtype=np.int64)
        exacte = True
    else:
        rng = np.random.default_rng(_graine_locale(graine, "aleatoire|" + cle))
        sous = np.argsort(rng.random((n_echantillon, n)), axis=1)[:, :m]
        exacte = False
    vals = rel[sous].mean(axis=1) - 1.0
    p05, med, p95 = (float(x) for x in np.quantile(vals, [0.05, 0.5, 0.95]))
    p_ge = pct = None
    if observe is not None:
        tol = 1e-12
        p_ge = float(np.mean(vals >= observe - tol))
        pct = float(np.mean(vals < observe - tol))
    return DistributionAleatoire(
        m, n, total, exacte, len(vals), float(vals.mean()), p05, med, p95, p_ge, pct
    )
