"""Revue indépendante : oracles recalculés en numpy/pandas/scipy, sans réutiliser les fonctions de
`tools/`. Trois jeux par outil : valeurs connues, graine fixe, cas limite.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest
from tools_helpers import apres, depuis_rendements, marche_aleatoire, serie

from amundi_agentic.tools import finance, momentum, risk
from amundi_agentic.tools.base import DegenerateSeriesError, ToolError

ALEA = marche_aleatoire(900, graine=7)
ALEA2 = marche_aleatoire(700, graine=123)


def _px(s, n):  # n+1 dernières clôtures (t = lendemain de la dernière barre)
    return s.to_numpy()[-(n + 1) :]


# ---------------------------------------------------------------- finance
@pytest.mark.parametrize("s,n", [(ALEA, 252), (ALEA, 63), (ALEA2, 100), (ALEA2, 5)])
def test_finance_oracle_graine_fixe(s, n):
    t = apres(s)
    p = _px(s, n)
    r = p[1:] / p[:-1] - 1
    cum = p[-1] / p[0] - 1
    ann = (1 + cum) ** (252 / n) - 1
    vol = np.std(r, ddof=1) * math.sqrt(252)
    rf = 0.03
    assert finance.cumulative_return(s, t, n).value == pytest.approx(cum, rel=1e-12)
    assert finance.annualized_return(s, t, n).value == pytest.approx(ann, rel=1e-12)
    assert finance.annualized_volatility(s, t, n).value == pytest.approx(vol, rel=1e-12)
    assert finance.sharpe_ratio(s, t, n, rf).value == pytest.approx((ann - rf) / vol, rel=1e-11)
    rfd = (1 + rf) ** (1 / 252) - 1
    dd = math.sqrt(np.mean(np.minimum(r - rfd, 0) ** 2)) * math.sqrt(252)
    assert finance.sortino_ratio(s, t, n, rf).value == pytest.approx((ann - rf) / dd, rel=1e-11)
    pic = np.maximum.accumulate(p)
    mdd = (p / pic - 1).min()
    assert finance.max_drawdown(s, t, n).value["max_drawdown"] == pytest.approx(mdd, rel=1e-12)
    assert finance.current_drawdown(s, t, n).value == pytest.approx(p[-1] / p.max() - 1, rel=1e-12)
    assert finance.calmar_ratio(s, t, n).value == pytest.approx(ann / abs(mdd), rel=1e-11)
    # dates pic / creux
    k = int(np.argmin(p / pic - 1))
    j = int(np.argmax(p[: k + 1]))
    idx = s.index[-(n + 1) :]
    res = finance.max_drawdown(s, t, n).value
    assert res["trough_date"] == idx[k].date() and res["peak_date"] == idx[j].date()


def test_finance_valeurs_connues_main():
    # 4 rendements : +10 %, -10 %, +10 %, -10 %  (prix 100, 110, 99, 108.9, 98.01)
    s = depuis_rendements([0.1, -0.1, 0.1, -0.1])
    t = apres(s)
    assert finance.cumulative_return(s, t, 4).value == pytest.approx(98.01 / 100 - 1)
    ann = (98.01 / 100) ** (252 / 4) - 1
    assert finance.annualized_return(s, t, 4).value == pytest.approx(ann)
    # écart-type ddof=1 de (0.1,-0.1,0.1,-0.1) approx. : moyenne ~ 0 (calculée par les prix)
    r = np.array([0.1, -0.1, 0.1, -0.1])
    assert finance.annualized_volatility(s, t, 4).value == pytest.approx(
        r.std(ddof=1) * math.sqrt(252)
    )
    # perte maximale : pic 110 (idx1) ; creux final 98,01 (idx4) : 98,01/110 - 1
    res = finance.max_drawdown(s, t, 4).value
    assert res["max_drawdown"] == pytest.approx(98.01 / 110 - 1)
    assert res["peak_date"] == s.index[1].date() and res["trough_date"] == s.index[4].date()


def test_finance_horizon_non_multiple_de_252_et_n_court():
    # n = 1 rendement : (1+R)^252 - 1 ; l'annualisation d'une seule séance est correcte
    # mais l'écart-type exige >= 2 rendements : erreur explicite
    s = serie([100, 101, 102])
    t = apres(s)
    assert finance.annualized_return(s, t, 1).value == pytest.approx((102 / 101) ** 252 - 1)
    with pytest.raises(ToolError):
        finance.annualized_volatility(s, t, 1)


def test_sharpe_glissant_oracle_pandas():
    s, t = ALEA, apres(ALEA)
    w, rf = 63, 0.04
    r = s.pct_change()
    rfd = (1 + rf) ** (1 / 252) - 1
    att = (r.rolling(w).mean() - rfd) / r.rolling(w).std(ddof=1)
    att = att.iloc[w:]
    got = finance.rolling_sharpe(s, t, w, rf).value
    pd.testing.assert_series_equal(got, att.rename("rolling_sharpe"), rtol=1e-10, check_freq=False)
    got_a = finance.rolling_sharpe(s, t, w, rf, annualize=True).value
    pd.testing.assert_series_equal(
        got_a, (att * math.sqrt(252)).rename("rolling_sharpe"), rtol=1e-10, check_freq=False
    )


def test_cas_limite_taux_sans_risque_negatif_et_invalides():
    # un taux négatif (ex. EONIA 2020) est légitime
    assert finance.daily_rf(-0.005) == pytest.approx((0.995) ** (1 / 252) - 1)
    for bad in (float("nan"), -1.0, float("inf")):
        with pytest.raises(ValueError):
            finance.daily_rf(bad)


def test_serie_croissante_monotone_perte_nulle_calmar_erreur_pas_inf():
    s = serie(np.linspace(100, 120, 60))
    with pytest.raises(ToolError):
        finance.calmar_ratio(s, apres(s), 50)
    assert finance.max_drawdown(s, apres(s), 50).value["max_drawdown"] == 0.0


def test_serie_plate_monetaire_aucun_nombre_invente():
    s = serie([100.0] * 300)
    t = apres(s)
    assert finance.annualized_return(s, t, 252).value == 0.0
    assert finance.annualized_volatility(s, t, 252).value == 0.0
    for f in (finance.sharpe_ratio, finance.sortino_ratio, finance.calmar_ratio):
        with pytest.raises(ToolError):
            f(s, t, 252)
    assert finance.max_drawdown(s, t, 252).value["max_drawdown"] == 0.0
    out = momentum.valuation_summary(s, t, 0.0).value
    assert {"sharpe", "sortino", "calmar"} <= set(out["manquants"])
    # avec R_f > 0, le Sortino d'une série plate valait environ -16 (défini mais sans sens) ;
    # depuis le garde-fou de volatilité minimale (1e-4), il est REFUSÉ explicitement
    for rf in (0.0, 0.02, -0.005):
        with pytest.raises(DegenerateSeriesError):
            finance.sortino_ratio(s, t, 252, rf)
        with pytest.raises(DegenerateSeriesError):
            finance.sharpe_ratio(s, t, 252, rf)
    out2 = momentum.valuation_summary(s, t, 0.02).value
    assert {"sharpe", "sortino", "calmar"} <= set(out2["manquants"])
    assert "DegenerateSeriesError" in out2["manquants"]["sortino"]
    assert not any(
        math.isnan(v) or math.isinf(v) for v in out["valeurs"].values() if isinstance(v, float)
    )


# ---------------------------------------------------------------- momentum
@pytest.mark.parametrize("s", [ALEA, ALEA2])
def test_momentum_oracle(s):
    t = apres(s)
    p = s.to_numpy()
    for mois, n in ((1, 21), (3, 63), (6, 126), (12, 252)):
        assert momentum.momentum(s, t, mois).value == pytest.approx(p[-1] / p[-1 - n] - 1)
    assert momentum.momentum_12_1(s, t).value == pytest.approx(p[-1 - 21] / p[-1 - 252] - 1)
    sma = p[-200:].mean()
    r = momentum.trend_vs_sma(s, t, 200).value
    assert r["ecart_sma"] == pytest.approx(p[-1] / sma - 1)
    assert r["sma"] == pytest.approx(sma)


def test_momentum_borne_exacte_historique_minimal():
    s = serie(np.arange(100, 100 + 253, dtype=float))  # 253 barres : juste assez pour 12 mois
    t = apres(s)
    assert momentum.momentum(s, t, 12).value == pytest.approx(352 / 100 - 1)
    with pytest.raises(ToolError):
        momentum.momentum(s.iloc[1:], t, 12)  # 252 barres : insuffisant


# ---------------------------------------------------------------- risque
@pytest.mark.parametrize("s", [ALEA, ALEA2])
def test_risque_oracle_vol_var_cvar(s):
    t = apres(s)
    p = _px(s, 252)
    r = p[1:] / p[:-1] - 1
    for lvl in (0.90, 0.95, 0.99):
        q = np.quantile(r, 1 - lvl, method="linear")
        assert risk.historical_var(s, t, 252, lvl).value == pytest.approx(-q, rel=1e-12)
        assert risk.historical_cvar(s, t, 252, lvl).value == pytest.approx(
            -r[r <= q].mean(), rel=1e-12
        )
        assert (
            risk.historical_cvar(s, t, 252, lvl).value >= risk.historical_var(s, t, 252, lvl).value
        )
    p21 = _px(s, 21)
    assert risk.realized_volatility(s, t).value == pytest.approx(
        np.std(p21[1:] / p21[:-1] - 1, ddof=1) * math.sqrt(252), rel=1e-12
    )


def test_ewma_oracle_pandas_ewm_demi_vie():
    s, t = ALEA, apres(ALEA)
    n = len(s)
    # clôtures hebdomadaires (5 séances) ancrées sur la dernière barre, au plus 260 rendements
    pos = np.arange(n - 1, -1, -5)[::-1][-261:]
    w = s.to_numpy()[pos]
    r = pd.Series(w[1:] / w[:-1] - 1)
    # pandas ewm : poids 0,5^(âge/13) ; adjust=True normalise. Variance à moyenne nulle.
    ewm_var = (r**2).ewm(halflife=13, adjust=True).mean().iloc[-1]
    assert risk.ewma_volatility(s, t).value == pytest.approx(
        math.sqrt(ewm_var) * math.sqrt(52), rel=1e-10
    )


def test_ewma_lambda_equivalent():
    # demi-vie 13 sem. <=> lambda = 0,5^(1/13) ~ 0,9480 ; le poids de la semaine 13 est la moitié
    s, t = ALEA, apres(ALEA)
    lam = 0.5 ** (1 / 13)
    n = len(s)
    pos = np.arange(n - 1, -1, -5)[::-1][-261:]
    w = s.to_numpy()[pos]
    r = (w[1:] / w[:-1] - 1)[::-1]
    poids = lam ** np.arange(len(r))
    att = math.sqrt((poids * r**2).sum() / poids.sum() * 52)
    assert risk.ewma_volatility(s, t).value == pytest.approx(att, rel=1e-10)


def test_correlation_oracle_pandas_quotidien_et_hebdo():
    rng = np.random.default_rng(5)
    base = marche_aleatoire(400, graine=1)
    df = pd.DataFrame(
        {
            "A": base,
            "B": base * np.exp(np.cumsum(rng.normal(0, 0.01, len(base)))),
            "C": marche_aleatoire(400, graine=3),
        }
    )
    t = apres(df)
    got = risk.correlation_matrix(df, t, 63).value
    att = df.iloc[-64:].pct_change().iloc[1:].corr()
    np.testing.assert_allclose(got.to_numpy(), att.to_numpy(), atol=1e-12)
    gw = risk.correlation_matrix(df, t, 20, "weekly").value
    pos = [len(df) - 1 - 5 * k for k in range(20, -1, -1)]
    attw = df.iloc[pos].pct_change().iloc[1:].corr()
    np.testing.assert_allclose(gw.to_numpy(), attw.to_numpy(), atol=1e-12)
    assert np.allclose(got.to_numpy(), got.to_numpy().T) and np.allclose(np.diag(got), 1.0)


def test_regime_oracle_independant():
    s, t = ALEA, apres(ALEA)
    p = s.to_numpy()
    r = p[1:] / p[:-1] - 1
    n = len(r)

    def vol(j):  # vol 21 séances se terminant au rendement j
        return np.std(r[j - 20 : j + 1], ddof=1) * math.sqrt(252)

    cur = vol(n - 1)
    dist = np.array([vol(n - 1 - 5 * k) for k in range(1, 157)])
    p50, p80 = np.percentile(dist, [50, 80])
    res = risk.volatility_regime(s, t).value
    assert res.volatility == pytest.approx(cur, rel=1e-12)
    assert (res.p_low, res.p_high) == (pytest.approx(p50), pytest.approx(p80))
    assert res.n_weeks == 156
    rang = (np.sum(dist < cur) + 0.5 * np.sum(dist == cur)) / 156
    assert res.percentile_rank == pytest.approx(rang)
    assert res.regime == ("haut" if cur > p80 else "normal")


def test_regime_valeur_courante_exclue_effet_mesurable():
    # Un pic de volatilité courant ne doit pas faire monter son propre centile 80
    rng = np.random.default_rng(11)
    r = rng.normal(0, 0.005, 800)
    r[-10:] = rng.normal(0, 0.05, 10)
    s = depuis_rendements(r)
    res = risk.volatility_regime(s, apres(s)).value
    assert res.regime == "haut" and res.volatility > res.p_high
    assert res.percentile_rank == 1.0


def test_regime_serie_plate_ne_declenche_rien():
    s = serie([100.0] * 900)
    res = risk.volatility_regime(s, apres(s)).value
    assert res.regime == "normal" and res.volatility == 0.0 and res.percentile_rank == 0.5


# ---------------------------------------------------------------- seuil de creux et flottants
def test_tolerance_flottante_90_sur_100_declenche_le_seuil_de_10_pourcents():
    """90/100-1 vaut -0,09999999999999998 en flottant : avec la tolérance de 1e-9, le creux de
    10 % déclenche bien « moderee » (avant correction : « aucune »)."""
    creux = 90.0 / 100.0 - 1.0
    assert -creux < 0.10  # le piège flottant existe toujours dans l'arithmétique brute
    assert risk._niveau(-creux, 0.10, 0.20) == "moderee"
    # 80/100-1 = -0,19999999999999996 : seuil élevé de 20 %
    assert risk._niveau(-(80.0 / 100.0 - 1.0), 0.10, 0.20) == "elevee"
    # un creux réellement inférieur ne déclenche pas
    assert risk._niveau(0.0999, 0.10, 0.20) == "aucune"


@pytest.mark.parametrize("seuil_mod,seuil_haut", [(0.10, 0.20), (0.80, 0.95), (25.0, 35.0)])
def test_tolerance_des_seuils_de_part_et_d_autre_oracle_independant(seuil_mod, seuil_haut):
    tol = 1e-9
    for seuil, niveau in ((seuil_mod, "moderee"), (seuil_haut, "elevee")):
        # oracle écrit ici : atteint ssi valeur + 1e-9 >= seuil
        assert risk._niveau(seuil, seuil_mod, seuil_haut) == niveau
        assert risk._niveau(seuil - tol / 2, seuil_mod, seuil_haut) == niveau  # dans la tolérance
        assert risk._niveau(seuil - 1e-6, seuil_mod, seuil_haut) != niveau  # bien en dessous
        assert risk._niveau(seuil + 1e-6, seuil_mod, seuil_haut) == niveau
    # niveau inférieur : très en dessous du seuil modéré
    assert risk._niveau(seuil_mod - 1e-6, seuil_mod, seuil_haut) == "aucune"
    assert risk._niveau(seuil_mod - 1e-3, seuil_mod, seuil_haut) == "aucune"


def test_seuil_exact_a_la_decimale_pres_vol_rang():
    # rang exactement égal au seuil 0,80 : modérée
    assert risk._niveau(0.80, 0.80, 0.95) == "moderee"
    # nextafter(0,80 ; 0) est à ~1e-16 du seuil : DANS la tolérance de 1e-9, donc modérée
    assert risk._niveau(float(np.nextafter(0.80, 0)), 0.80, 0.95) == "moderee"
    # à 1e-6 en dessous : hors tolérance, pas d'alerte ; à 1e-9 pile, frontière numérique
    assert risk._niveau(0.80 - 1e-6, 0.80, 0.95) == "aucune"
    assert risk._niveau(0.95 - 1e-6, 0.80, 0.95) == "moderee"
    assert risk._niveau(float(np.nextafter(0.95, 0)), 0.80, 0.95) == "elevee"
    # un rang réel k/156 n'est jamais à moins de 1e-9 d'un seuil sans lui être égal : le plus
    # proche de 0,80 est 125/156 = 0,8013 (écart 1,3e-3 >> tolérance)
    assert min(abs(k / 156 - 0.80) for k in range(157)) > 1e-3


def test_facteur_h_et_alerte_inconnue():
    assert [risk.confidence_factor_h(a) for a in ("aucune", "moderee", "elevee")] == [1.0, 0.8, 0.6]
    for bad in ("", "ELEVEE", None, "critique"):
        with pytest.raises(ToolError):
            risk.confidence_factor_h(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------- macro unités
def test_macro_unites_fred_divise_par_cent_vix_non_divise():
    from amundi_agentic.tools.macro_regime import macro_regime

    d = pd.bdate_range("2023-01-02", "2024-06-28")

    def sr(val):
        return pd.DataFrame({"date": d, "value": val, "available_from": d + pd.Timedelta(days=1)})

    series = {
        "fred:DGS10": sr(4.0),
        "fred:DGS2": sr(4.5),
        "fred:VIXCLS": sr(20.0),
        "fred:BAMLH0A0HYM2": sr(3.5),
        "fred:UNRATE": sr(4.0),
    }
    res = macro_regime(series, date(2024, 7, 1)).value
    assert res.indicateurs["taux_10y"] == pytest.approx(0.04)
    assert res.indicateurs["ecart_credit_hy"] == pytest.approx(0.035)
    assert res.indicateurs["chomage"] == pytest.approx(0.04)
    assert res.indicateurs["vix"] == 20.0
    assert res.indicateurs["pente_us_10y_2y"] == pytest.approx(-0.005)
    assert res.drapeaux["courbe_inversee_us"] is True
    assert res.indicateurs["taux_10y_var_12m"] == pytest.approx(0.0)
