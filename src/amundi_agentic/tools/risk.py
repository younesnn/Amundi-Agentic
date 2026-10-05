# ruff: noqa: E501
"""Risque : volatilité (réalisée, EWMA), VaR et CVaR historiques, corrélations, régime de volatilité,
alertes par seuils et facteur h (L1 §4, §6.4, §10.1 ; D-013, D-015 ; EX-O1-01, EX-O1-04).

Les alertes sont calculées ICI, en Python : le LLM les commente, il ne les produit ni ne les modifie.

| Outil | Formule | Unité |
| --- | --- | --- |
| `realized_volatility` | std(r sur 21 séances, ddof=1) x sqrt(252) | décimal par an |
| `ewma_volatility` | sqrt(sum_a w_a r_a^2 / sum_a w_a) x sqrt(52), w_a = 0,5^(a / 13), a = 0 pour la semaine la plus récente, rendements HEBDOMADAIRES | décimal par an |
| `historical_var` | -quantile_{1-niveau}(r) (interpolation linéaire de numpy) | perte, décimal |
| `historical_cvar` | -moyenne(r | r <= quantile_{1-niveau}(r)) | perte, décimal |
| `correlation_matrix` | corrélation de Pearson des rendements simples de la fenêtre | [-1, 1] |
| `volatility_regime` | centiles 50 et 80 de la volatilité réalisée 21 séances échantillonnée chaque semaine sur 156 semaines AVANT la dernière séance connue, avec hystérésis | régime |
| `risk_report` | alertes par actif (max des niveaux déclenchés), régime, indicateurs, seuils | « aucune », « moderee », « elevee » |
| `confidence_factor_h` | h = 1,0 / 0,8 / 0,6 selon l'alerte (L1 §6.4) | facteur |

Hypothèses (H) :
* H1 : une « semaine » = 5 séances consécutives (échantillonnage par position depuis la dernière
  séance connue), ce qui évite toute dépendance au calendrier civil et aux jours fériés. Les
  rendements hebdomadaires de l'EWMA sont ceux de ces clôtures espacées de 5 séances.
* H2 : EWMA à moyenne nulle (convention RiskMetrics), demi-vie de 13 semaines (D-013), historique
  limité à 260 semaines (D-013), au moins 26 rendements hebdomadaires.
* H3 : régime de volatilité (L1 §10.1) : la distribution de référence est formée des 156 valeurs
  hebdomadaires qui PRÉCÈDENT la dernière séance connue (la valeur courante est exclue) ; au moins
  104 valeurs sont exigées (sinon `InsufficientDataError`). Régime « haut » si volatilité
  courante > centile 80 ; retour à « normal » si < centile 50 ; entre les deux, le régime
  précédent est conservé (hystérésis). Sans régime précédent connu, la zone intermédiaire donne
  « normal ». Le régime est une MACHINE À ÉTATS : l'état précédent est porté explicitement par
  l'appelant (`previous`), que le backtest et le live persistent date après date et journalisent
  (aucun état caché dans l'outil). Repli sans état fourni : rejeu de la machine sur les
  `DEFAULT_REPLAY_WEEKS` = 52 dernières semaines (H, à geler dans `config/debate.yaml`) ; le résultat
  dépend alors de cette profondeur (constat du reviewer : à t fixé, rejeu 0 et rejeu >= 4 peuvent
  différer). Chaque sortie dit d'où vient le régime : `VolRegime.origine` = « etat_fourni »,
  « rejeu » ou « sans_etat » (aucun état ni rejeu possible), avec la profondeur demandée et le
  nombre de pas réellement calculés ; ces valeurs sont aussi dans `ToolMeta.params`.
  `replay_weeks=0` explicite force « sans_etat ».
* H4 : seuils d'alerte par défaut de `RiskThresholds` : hypothèses de conception, à fixer dans
  `config/debate.yaml` (aucune valeur n'est une mesure). Un seuil est atteint dès que la valeur
  + `THRESHOLD_TOLERANCE` (1e-9, H) est >= au seuil, pour absorber l'erreur flottante
  (90/100 - 1 = -0,09999999999999998 doit déclencher le seuil de 10 %) ; valable pour le creux, le
  rang de volatilité et le VIX.
* H6 : `risk_report.sources` contient une `ToolMeta` par série effectivement utilisée (actif,
  benchmark pour le régime, VIX), avec sa fenêtre réelle et son nombre d'observations ; la méta
  globale couvre du début de la plus ancienne fenêtre à la dernière donnée la plus récente
  (`n_obs` = somme des observations des sources). `aggregate_alerts_by_class` donne la pire
  alerte par classe (L1 §6.4) à partir d'une correspondance actif -> classe fournie par l'appelant.
* H5 : le rang centile d'une volatilité est le rang « moyen » dans la distribution de référence :
  (nombre de valeurs strictement inférieures + moitié des valeurs égales) / effectif. Une série
  plate (volatilité nulle partout) a donc le rang 0,5 et non 1. Limite : un actif quasi sans
  volatilité (monétaire) a un rang bruité ; sa vraie protection est le seuil de creux.

Cas limites : historique insuffisant -> `InsufficientDataError` ; NaN dans la fenêtre ->
`MissingDataError` ; colonne de rendements constants (corrélation) -> `DegenerateSeriesError`.
Dans `risk_report`, un actif dont un indicateur ne peut être calculé est listé dans
`indisponibles` avec la raison et n'a PAS d'alerte (jamais « aucune » par défaut).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd

from amundi_agentic.tools.base import (
    TRADING_DAYS,
    WEEKS_PER_YEAR,
    DegenerateSeriesError,
    InsufficientDataError,
    MissingDataError,
    ToolError,
    ToolMeta,
    ToolResult,
    known_before,
    known_macro,
    make_meta,
    sample_std,
    series_label,
    simple_returns,
    trailing_prices,
)

SESSIONS_PER_WEEK = 5
THRESHOLD_TOLERANCE = 1e-9  # H : tolérance flottante des seuils d'alerte
DEFAULT_REPLAY_WEEKS = 52  # H : profondeur du rejeu de repli du régime (gelée en configuration)
Alert = Literal["aucune", "moderee", "elevee"]
Regime = Literal["normal", "haut"]
_ORDRE: dict[str, int] = {"aucune": 0, "moderee": 1, "elevee": 2}

# L1 §6.4 (H) : facteur h appliqué à la confiance d'une vue selon l'alerte sur la classe de l'actif
DEFAULT_H: dict[str, float] = {"aucune": 1.0, "moderee": 0.8, "elevee": 0.6}


# ------------------------------------------------------------------------------ volatilités
def realized_volatility(prices: pd.Series, as_of: date, window: int = 21) -> ToolResult[float]:
    """Volatilité réalisée annualisée sur `window` séances (21 par défaut) : std x sqrt(252)."""
    w = trailing_prices(prices, as_of, window)
    vol = sample_std(simple_returns(w).to_numpy()) * np.sqrt(TRADING_DAYS)
    return ToolResult(
        float(vol),
        make_meta(
            "realized_volatility",
            as_of,
            w.index,
            len(w),
            window=window,
            series=series_label(prices),
        ),
    )


def _weekly_prices(prices: pd.Series, as_of: date, max_weeks: int, min_weeks: int) -> pd.Series:
    """Clôtures espacées de 5 séances en remontant depuis la dernière séance connue (H1)."""
    connu = known_before(prices, as_of, "prix")
    n = len(connu)
    n_ret = min(max_weeks, (n - 1) // SESSIONS_PER_WEEK)
    if n_ret < min_weeks:
        raise InsufficientDataError(
            f"EWMA : {max(n_ret, 0)} rendements hebdomadaires possibles, {min_weeks} requis"
        )
    pos = [n - 1 - SESSIONS_PER_WEEK * k for k in range(n_ret, -1, -1)]
    w = connu.iloc[pos].astype(float)
    if w.isna().any():
        raise MissingDataError("EWMA : clôture manquante sur la grille hebdomadaire")
    if (w <= 0).any():
        raise DegenerateSeriesError("EWMA : prix non strictement positif")
    return w


def ewma_volatility(
    prices: pd.Series,
    as_of: date,
    half_life_weeks: float = 13.0,
    max_weeks: int = 260,
    min_weeks: int = 26,
) -> ToolResult[float]:
    """Volatilité EWMA annualisée (demi-vie 13 semaines, D-013) sur rendements hebdomadaires (H2)."""
    if half_life_weeks <= 0:
        raise ValueError("la demi-vie doit être positive")
    w = _weekly_prices(prices, as_of, max_weeks, min_weeks)
    r = simple_returns(w).to_numpy()[::-1]  # r[0] = semaine la plus récente
    poids = 0.5 ** (np.arange(len(r)) / half_life_weeks)
    var = float(np.sum(poids * r**2) / np.sum(poids))
    return ToolResult(
        float(np.sqrt(var) * np.sqrt(WEEKS_PER_YEAR)),
        make_meta(
            "ewma_volatility",
            as_of,
            w.index,
            len(w),
            half_life_weeks=half_life_weeks,
            max_weeks=max_weeks,
            series=series_label(prices),
        ),
    )


# ------------------------------------------------------------------------------ VaR / CVaR
def _tail(prices: pd.Series, as_of: date, window: int, level: float):
    if not 0.5 <= level < 1.0:
        raise ValueError("niveau de confiance attendu dans [0,5 ; 1[")
    w = trailing_prices(prices, as_of, window)
    r = simple_returns(w).to_numpy()
    q = float(np.percentile(r, (1.0 - level) * 100.0))
    return w, r, q


def historical_var(
    prices: pd.Series, as_of: date, window: int = 252, level: float = 0.95
) -> ToolResult[float]:
    """VaR historique à 1 jour : -quantile(1 - niveau) des rendements ; perte exprimée positive.

    Négative seulement si même le quantile bas des rendements est positif (aucune perte au seuil).
    """
    w, _, q = _tail(prices, as_of, window, level)
    return ToolResult(
        -q,
        make_meta(
            "historical_var",
            as_of,
            w.index,
            len(w),
            window=window,
            level=level,
            series=series_label(prices),
        ),
    )


def historical_cvar(
    prices: pd.Series, as_of: date, window: int = 252, level: float = 0.95
) -> ToolResult[float]:
    """CVaR historique (expected shortfall) : -moyenne des rendements <= quantile ; perte positive."""
    w, r, q = _tail(prices, as_of, window, level)
    return ToolResult(
        float(-np.mean(r[r <= q])),
        make_meta(
            "historical_cvar",
            as_of,
            w.index,
            len(w),
            window=window,
            level=level,
            series=series_label(prices),
        ),
    )


# ------------------------------------------------------------------------------ corrélations
def correlation_matrix(
    prices: pd.DataFrame,
    as_of: date,
    window: int = 63,
    frequency: Literal["daily", "weekly"] = "daily",
) -> ToolResult[pd.DataFrame]:
    """Corrélations de Pearson des rendements simples sur `window` rendements.

    `weekly` : rendements entre clôtures espacées de 5 séances (H1) ; recommandé quand les places
    ferment à des heures différentes (D-013). Un NaN sur une ligne utilisée, une colonne constante
    ou un historique trop court lèvent une erreur ; aucune ligne n'est écartée en silence.
    """
    if frequency not in ("daily", "weekly"):
        raise ValueError("frequency : 'daily' ou 'weekly'")
    if window < 3:
        raise ValueError("fenêtre de corrélation : au moins 3 rendements")
    connu = known_before(prices, as_of, "prix")
    pas = 1 if frequency == "daily" else SESSIONS_PER_WEEK
    n = len(connu)
    besoin = pas * window + 1
    if n < besoin:
        raise InsufficientDataError(f"corrélations : {n} séances connues, {besoin} requises")
    pos = [n - 1 - pas * k for k in range(window, -1, -1)]
    w = connu.iloc[pos].astype(float)
    if w.isna().any().any():
        cols = [str(c) for c in w.columns[w.isna().any()]]
        raise MissingDataError(f"corrélations : valeurs manquantes dans la fenêtre pour {cols}")
    if (w <= 0).any().any():
        raise DegenerateSeriesError("corrélations : prix non strictement positif")
    r = w.to_numpy()[1:] / w.to_numpy()[:-1] - 1.0
    if np.any(np.ptp(r, axis=0) == 0.0):
        cols = [str(c) for c in w.columns[np.ptp(r, axis=0) == 0.0]]
        raise DegenerateSeriesError(f"corrélation non définie : rendements constants pour {cols}")
    c = np.corrcoef(r, rowvar=False)
    c = np.atleast_2d(c)
    out = pd.DataFrame(c, index=w.columns, columns=w.columns)
    return ToolResult(
        out,
        make_meta(
            "correlation_matrix",
            as_of,
            w.index,
            len(w),
            window=window,
            frequency=frequency,
            series=series_label(prices),
        ),
    )


# ------------------------------------------------------------------------------ régime
@dataclass(frozen=True)
class VolRegime:
    regime: Regime
    volatility: float  # annualisée, décimal
    p_low: float  # centile bas (50) de la distribution de référence
    p_high: float  # centile haut (80)
    percentile_rank: float  # H5
    n_weeks: int  # taille de la distribution de référence
    changed: bool | None  # vs régime précédent ; None si aucun précédent
    origine: Literal["etat_fourni", "rejeu", "sans_etat"] = "sans_etat"  # d'où vient l'état
    replay_weeks_requested: int = 0  # profondeur de rejeu demandée (0 si état fourni)
    replay_steps_computed: int = 0  # pas de rejeu réellement calculés (historique suffisant)


def _vol_distribution(
    c: np.ndarray, win: int, weeks: int, min_weeks: int
) -> tuple[float, np.ndarray]:
    """Volatilité courante et distribution de référence (H3) à partir de clôtures sans NaN."""
    r = c[1:] / c[:-1] - 1.0
    last = len(r) - 1
    if last < win - 1:
        raise InsufficientDataError(f"régime : {len(r)} rendements, {win} requis")

    def vol(j: int) -> float:
        return float(np.std(r[j - win + 1 : j + 1], ddof=1) * np.sqrt(TRADING_DAYS))

    idx = [last - SESSIONS_PER_WEEK * k for k in range(1, weeks + 1)]
    idx = [j for j in idx if j - win + 1 >= 0]
    if len(idx) < min_weeks:
        raise InsufficientDataError(
            f"régime : {len(idx)} valeurs hebdomadaires de référence, {min_weeks} requises"
        )
    return vol(last), np.array([vol(j) for j in reversed(idx)])


def _mid_rank(dist: np.ndarray, v: float) -> float:
    return float((np.sum(dist < v) + 0.5 * np.sum(dist == v)) / len(dist))


def _next_regime(v: float, p_low: float, p_high: float, prev: Regime | None) -> Regime:
    if v > p_high:
        return "haut"
    if prev == "haut" and v >= p_low:
        return "haut"  # hystérésis : on ne revient à « normal » que sous le centile bas
    return "normal"


def _clean_tail(prices: pd.Series, as_of: date, n_obs: int) -> pd.Series:
    connu = known_before(prices, as_of, "prix")
    if len(connu) < 2:
        raise InsufficientDataError("historique de moins de 2 séances")
    tail = connu.iloc[-n_obs:].astype(float)
    if tail.isna().any():
        raise MissingDataError("régime : valeur manquante dans la fenêtre (aucun remplissage)")
    if (tail <= 0).any():
        raise DegenerateSeriesError("régime : prix non strictement positif")
    return tail


def volatility_regime(
    prices: pd.Series,
    as_of: date,
    previous: Regime | None = None,
    vol_window: int = 21,
    history_weeks: int = 156,
    min_weeks: int = 104,
    low_pct: float = 50.0,
    high_pct: float = 80.0,
    replay_weeks: int | None = None,
) -> ToolResult[VolRegime]:
    """Régime de volatilité de la série (le benchmark) à t, règle de L1 §10.1 (H3).

    Machine à états : `previous` (régime à la date de contrôle précédente) est porté par l'appelant.
    Sans `previous`, repli : rejeu sur `replay_weeks` semaines (None -> `DEFAULT_REPLAY_WEEKS`, H ;
    0 -> aucun rejeu, zone intermédiaire = « normal »). `previous` fourni avec `replay_weeks` > 0
    est refusé. La provenance de l'état est dans `VolRegime.origine` et `ToolMeta.params`.
    """
    if not 0 < low_pct < high_pct < 100:
        raise ValueError("centiles : 0 < bas < haut < 100")
    if replay_weeks is not None and (
        replay_weeks < 0 or (replay_weeks > 0 and previous is not None)
    ):
        raise ValueError("replay_weeks > 0 exige previous=None (le rejeu part sans état)")
    if previous is not None:
        profondeur = 0
    else:
        profondeur = DEFAULT_REPLAY_WEEKS if replay_weeks is None else replay_weeks
    n_obs = (history_weeks + profondeur) * SESSIONS_PER_WEEK + vol_window + 2
    tail = _clean_tail(prices, as_of, n_obs)
    c = tail.to_numpy()

    def etat(
        arr: np.ndarray, prev: Regime | None
    ) -> tuple[Regime, float, float, float, float, int]:
        v, dist = _vol_distribution(arr, vol_window, history_weeks, min_weeks)
        lo, hi = (float(x) for x in np.percentile(dist, [low_pct, high_pct]))
        rang = float(_mid_rank(dist, v))
        return _next_regime(v, lo, hi, prev), v, lo, hi, rang, len(dist)

    prev = previous
    pas = 0
    for m in range(profondeur, 0, -1):  # rejeu : semaines t-m, ..., t-1 (positions par 5 séances)
        fin = len(c) - SESSIONS_PER_WEEK * m
        try:
            prev = etat(c[:fin], prev)[0]
            pas += 1
        except InsufficientDataError:
            continue  # pas assez d'historique à cette date : la machine démarre plus tard
    regime, v, lo, hi, rang, n = etat(c, prev)
    origine = "etat_fourni" if previous is not None else ("rejeu" if pas > 0 else "sans_etat")
    return ToolResult(
        VolRegime(
            regime,
            v,
            lo,
            hi,
            rang,
            n,
            None if prev is None else regime != prev,
            origine,
            profondeur,
            pas,
        ),  # fmt: skip
        make_meta(
            "volatility_regime",
            as_of,
            tail.index,
            len(tail),
            vol_window=vol_window,
            history_weeks=history_weeks,
            low_pct=low_pct,
            high_pct=high_pct,
            replay_weeks=profondeur,
            replay_steps=pas,
            origine=origine,
            previous=previous,
            series=series_label(prices),
        ),
    )


# ------------------------------------------------------------------------------ alertes
@dataclass(frozen=True)
class RiskThresholds:
    """Seuils d'alerte (H4) : à lire dans `config/debate.yaml`, jamais dans le code des agents."""

    vol_rank_moderate: float = 0.80  # rang centile de la vol. 21 j dans sa distribution propre
    vol_rank_high: float = 0.95
    drawdown_moderate: float = 0.10  # creux courant (valeur absolue)
    drawdown_high: float = 0.20
    vix_moderate: float = 25.0  # points d'indice
    vix_high: float = 35.0
    vol_window: int = 21
    history_weeks: int = 156
    min_weeks: int = 104
    drawdown_window: int = 252
    regime_low_pct: float = 50.0
    regime_high_pct: float = 80.0
    vix_max_age_days: int = 10

    def __post_init__(self) -> None:
        if not 0 < self.vol_rank_moderate < self.vol_rank_high <= 1:
            raise ValueError("seuils de rang de volatilité : 0 < modéré < élevé <= 1")
        if not 0 < self.drawdown_moderate < self.drawdown_high < 1:
            raise ValueError("seuils de creux : 0 < modéré < élevé < 1")
        if not 0 < self.vix_moderate < self.vix_high:
            raise ValueError("seuils de VIX : 0 < modéré < élevé")

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> RiskThresholds:
        inconnus = set(m) - set(cls.__dataclass_fields__)
        if inconnus:
            raise ValueError(f"seuils inconnus : {sorted(inconnus)}")
        return cls(**m)

    def to_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class RiskReport:
    """Entrée de `RiskAssessment` (L1 §5.3) : tout est calculé, le LLM ne fait que commenter."""

    alertes: dict[str, Alert]
    indisponibles: dict[str, str]
    regime_volatilite: Regime | None
    indicateurs: dict[str, float]
    seuils: dict[str, float]
    alerte_marche: Alert | None = None
    sources: list[ToolMeta] = field(default_factory=list)  # une par série utilisée (H6)
    # `indisponibles` (interface historique, conservée) = actifs ET clés techniques (`__regime__`,
    # `__vix__`) -> raison. Séparation propre : `actifs_indisponibles` (noms d'actifs seulement, à
    # passer tel quel à `aggregate_alerts_by_class`) et `indisponibles_techniques` (clés techniques).
    actifs_indisponibles: list[str] = field(default_factory=list)
    indisponibles_techniques: dict[str, str] = field(default_factory=dict)


def _niveau(valeur: float, modere: float, eleve: float) -> Alert:
    """Niveau d'alerte ; un seuil est atteint si valeur + tolérance >= seuil (H4)."""
    v = valeur + THRESHOLD_TOLERANCE
    if v >= eleve:
        return "elevee"
    if v >= modere:
        return "moderee"
    return "aucune"


def _plus_grave(a: Alert, b: Alert) -> Alert:
    return a if _ORDRE[a] >= _ORDRE[b] else b


def risk_report(
    prices: pd.DataFrame,
    benchmark: pd.Series,
    as_of: date,
    thresholds: RiskThresholds | None = None,
    previous_regime: Regime | None = None,
    vix: pd.DataFrame | None = None,
    replay_weeks: int | None = None,
) -> ToolResult[RiskReport]:
    """Alertes par actif, régime de volatilité du benchmark, VIX (facultatif).

    Alerte d'un actif = niveau le plus grave parmi (a) rang centile de sa volatilité 21 séances dans
    sa propre distribution sur 156 semaines, (b) son creux courant sur 252 séances (H4). `vix` suit
    le format `DataView.macro_long` ; son niveau est évalué séparément (`alerte_marche`), il n'est
    pas fondu dans les alertes d'actifs. `previous_regime` / `replay_weeks` : voir `volatility_regime`.
    `RiskReport.sources` : une `ToolMeta` par série utilisée (H6).
    """
    th = thresholds or RiskThresholds()
    connu = known_before(prices, as_of, "prix")
    alertes: dict[str, Alert] = {}
    indisp: dict[str, str] = {}
    actifs_indispo: list[str] = []
    techniques: dict[str, str] = {}
    ind: dict[str, float] = {}
    n_obs = (th.history_weeks) * SESSIONS_PER_WEEK + th.vol_window + 2
    sources: list[ToolMeta] = []

    for col in connu.columns:
        nom = str(col)
        try:
            tail = _clean_tail(connu[col], as_of, max(n_obs, th.drawdown_window + 1))
            v, dist = _vol_distribution(
                tail.iloc[-n_obs:].to_numpy(), th.vol_window, th.history_weeks, th.min_weeks
            )
            rang = float(_mid_rank(dist, v))
            fen = tail.iloc[-(th.drawdown_window + 1) :]
            if len(fen) < th.drawdown_window + 1:
                raise InsufficientDataError("creux courant : historique plus court que la fenêtre")
            creux = float(fen.iloc[-1] / fen.max() - 1.0)
        except ToolError as e:
            indisp[nom] = f"{type(e).__name__} : {e}"
            actifs_indispo.append(nom)
            continue
        ind[f"vol{th.vol_window}:{nom}"] = v
        ind[f"vol_rang:{nom}"] = rang
        ind[f"creux_courant:{nom}"] = creux
        alertes[nom] = _plus_grave(
            _niveau(rang, th.vol_rank_moderate, th.vol_rank_high),
            _niveau(-creux, th.drawdown_moderate, th.drawdown_high),
        )
        # fenêtre réellement utilisée pour cet actif : l'union des fenêtres de volatilité et de creux
        sources.append(
            make_meta(
                "risk_report",
                as_of,
                tail.index,
                len(tail),
                series=nom,
                unit="alerte (aucune/moderee/elevee) ; vol. décimal par an ; creux décimal",
                vol_window=th.vol_window,
                history_weeks=th.history_weeks,
                drawdown_window=th.drawdown_window,
            )
        )

    regime: Regime | None = None
    try:
        res_rg = volatility_regime(
            benchmark,
            as_of,
            previous=previous_regime,
            vol_window=th.vol_window,
            history_weeks=th.history_weeks,
            min_weeks=th.min_weeks,
            low_pct=th.regime_low_pct,
            high_pct=th.regime_high_pct,
            replay_weeks=replay_weeks,
        )
        rg = res_rg.value
        regime = rg.regime
        ind["vol_benchmark"] = rg.volatility
        ind["vol_benchmark_p_bas"] = rg.p_low
        ind["vol_benchmark_p_haut"] = rg.p_high
        sources.append(res_rg.meta)
    except ToolError as e:
        indisp["__regime__"] = techniques["__regime__"] = f"{type(e).__name__} : {e}"

    marche: Alert | None = None
    if vix is not None:
        k = known_macro(vix, as_of, "vix")
        t = pd.Timestamp(as_of)
        if len(k) and (t - k["date"].iloc[-1]).days <= th.vix_max_age_days:
            niveau = float(k["value"].iloc[-1])
            ind["vix"] = niveau
            marche = _niveau(niveau, th.vix_moderate, th.vix_high)
            sources.append(
                make_meta(
                    "risk_report",
                    as_of,
                    k["date"].iloc[-1:],
                    1,
                    series="vix",
                    unit="points d'indice",
                )
            )
        else:
            indisp["__vix__"] = techniques["__vix__"] = (
                "VIX absent ou plus ancien que le délai maximal"
            )

    bornes = [pd.Timestamp(x) for m in sources for x in (m.window_start, m.last_data_date) if x]
    return ToolResult(
        RiskReport(
            alertes, indisp, regime, ind, th.to_dict(), marche, sources, actifs_indispo, techniques
        ),
        make_meta(
            "risk_report",
            as_of,
            pd.DatetimeIndex(bornes) if bornes else None,
            sum(m.n_obs for m in sources),
            previous_regime=previous_regime,
            replay_weeks=replay_weeks,
            series=series_label(prices),
        ),
    )


# ------------------------------------------------------------------------------ alertes par classe
@dataclass(frozen=True)
class ClassAlert:
    """Pire alerte d'une classe d'actifs (L1 §6.4) et actifs qui la causent."""

    alerte: Alert | None  # None : aucun actif de la classe n'a d'alerte calculable
    responsables: tuple[str, ...]  # actifs au niveau le plus grave (vide si « aucune » ou None)
    actifs: tuple[str, ...]  # tous les actifs de la classe avec une alerte
    indisponibles: tuple[str, ...]  # actifs de la classe dont l'alerte n'a pas pu être calculée


def aggregate_alerts_by_class(
    alertes: Mapping[str, str],
    asset_class: Mapping[str, str],
    indisponibles: Iterable[str] = (),
) -> dict[str, ClassAlert]:
    """Pire alerte par classe d'actifs (primaire et proxys d'une classe : L1 §6.4).

    `asset_class` (actif -> classe) est fourni par l'appelant, jamais codé en dur. Fonction pure et
    déterministe (classes et actifs triés). Un actif alerté ou indisponible absent de `asset_class`,
    ou un niveau d'alerte inconnu, lève `ToolError` : aucun actif n'est écarté en silence. Un actif
    indisponible n'abaisse pas l'alerte de sa classe, mais est listé ; une classe sans aucune
    alerte calculable a `alerte=None`.
    """
    indispo = sorted(set(indisponibles))
    for a in list(alertes) + indispo:
        if a not in asset_class:
            raise ToolError(f"actif sans classe dans la correspondance : {a!r}")
    for a, niveau in alertes.items():
        if niveau not in _ORDRE:
            raise ToolError(f"niveau d'alerte inconnu pour {a!r} : {niveau!r}")
    sortie: dict[str, ClassAlert] = {}
    for classe in sorted(set(asset_class[a] for a in list(alertes) + indispo)):
        membres = sorted(a for a in alertes if asset_class[a] == classe)
        manquants = tuple(a for a in indispo if asset_class[a] == classe)
        if not membres:
            sortie[classe] = ClassAlert(None, (), (), manquants)
            continue
        pire = max((alertes[a] for a in membres), key=lambda n: _ORDRE[n])
        resp = tuple(a for a in membres if alertes[a] == pire) if pire != "aucune" else ()
        sortie[classe] = ClassAlert(pire, resp, tuple(membres), manquants)  # type: ignore[arg-type]
    return sortie


def confidence_factor_h(alert: str, mapping: Mapping[str, float] | None = None) -> float:
    """Facteur h de L1 §6.4 (H) : 1,0 (aucune) ; 0,8 (modérée) ; 0,6 (élevée). Alerte inconnue : erreur."""
    m = dict(DEFAULT_H if mapping is None else mapping)
    if alert not in m:
        raise ToolError(f"alerte inconnue : {alert!r} (attendu : {sorted(m)})")
    return float(m[alert])
