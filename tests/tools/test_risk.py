"""tools/risk.py : volatilités, VaR/CVaR, corrélations, régime, alertes, facteur h.

Chaque valeur attendue est calculée à la main (commentaires) ou par une formule écrite dans le test.
"""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest
from tools_helpers import apres, depuis_rendements, marche_aleatoire, serie

from amundi_agentic.tools import risk
from amundi_agentic.tools.base import (
    DegenerateSeriesError,
    InsufficientDataError,
    MissingDataError,
    ToolError,
)

SQ252 = math.sqrt(252)


# ------------------------------------------------------------------ volatilité réalisée
def test_volatilite_realisee_21_jours():
    # 21 rendements : 11 de +1 % et 10 de -1 % ; moyenne 0,01/21 ;
    # variance = (21 x 1e-4 - 21 x (0,01/21)^2) / 20
    r = [0.01, -0.01] * 10 + [0.01]
    p = depuis_rendements(r)
    var = (21 * 1e-4 - 21 * (0.01 / 21) ** 2) / 20
    got = risk.realized_volatility(p, apres(p), window=21).value
    assert got == pytest.approx(math.sqrt(var) * SQ252, rel=1e-9)


# ------------------------------------------------------------------ EWMA
def _grille_hebdo():
    """16 clôtures : seules les positions 0, 5, 10, 15 (grille hebdomadaire) comptent."""
    vals = [50.0] * 16
    for pos, v in zip((0, 5, 10, 15), (100.0, 110.0, 99.0, 118.8), strict=True):
        vals[pos] = v
    return serie(vals)


def test_ewma_demi_vie_13_semaines():
    p = _grille_hebdo()  # rendements hebdomadaires 0,10 ; -0,10 ; 0,20 (du plus ancien au récent)
    lam = 0.5 ** (1 / 13)
    var = (0.20**2 + 0.10**2 * lam + 0.10**2 * lam**2) / (1 + lam + lam**2)
    got = risk.ewma_volatility(p, apres(p), min_weeks=3).value
    assert got == pytest.approx(math.sqrt(var) * math.sqrt(52), rel=1e-12)


def test_ewma_demi_vie_une_semaine():
    p = _grille_hebdo()
    var = (0.20**2 + 0.10**2 * 0.5 + 0.10**2 * 0.25) / 1.75  # poids 1 ; 1/2 ; 1/4
    got = risk.ewma_volatility(p, apres(p), half_life_weeks=1.0, min_weeks=3).value
    assert got == pytest.approx(math.sqrt(var) * math.sqrt(52), rel=1e-12)


def test_ewma_ne_lit_que_la_grille_hebdomadaire():
    p = _grille_hebdo()
    q = p.copy()
    q.iloc[[1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14]] = 12345.0  # hors grille : sans effet
    assert (
        risk.ewma_volatility(p, apres(p), min_weeks=3).value
        == risk.ewma_volatility(q, apres(q), min_weeks=3).value
    )


def test_ewma_historique_trop_court_ou_manquant():
    p = _grille_hebdo()
    with pytest.raises(InsufficientDataError):
        risk.ewma_volatility(p, apres(p))  # 26 semaines requises par défaut
    q = p.copy()
    q.iloc[5] = np.nan
    with pytest.raises(MissingDataError):
        risk.ewma_volatility(q, apres(q), min_weeks=3)


# ------------------------------------------------------------------ VaR et CVaR
def _pertes():
    # 20 rendements : -5 %, -3 % et dix-huit fois +1 %
    return depuis_rendements([0.01] * 5 + [-0.05] + [0.01] * 6 + [-0.03] + [0.01] * 7)


def test_var_historique_95():
    # quantile 5 % (interpolation linéaire, n = 20) : indice 0,95 -> -0,05 + 0,95 x 0,02 = -0,031
    p = _pertes()
    assert risk.historical_var(p, apres(p), window=20, level=0.95).value == pytest.approx(0.031)


def test_cvar_historique_95():
    # seul -5 % est <= -3,1 % (-3 % est au-dessus) : CVaR = 5 %
    p = _pertes()
    assert risk.historical_cvar(p, apres(p), window=20, level=0.95).value == pytest.approx(0.05)


def test_cvar_au_moins_egale_a_la_var():
    p = marche_aleatoire(400)
    v = risk.historical_var(p, apres(p), 252).value
    c = risk.historical_cvar(p, apres(p), 252).value
    assert c >= v


def test_var_cas_limites():
    p = _pertes()
    with pytest.raises(InsufficientDataError):
        risk.historical_var(p, apres(p), window=252)
    with pytest.raises(ValueError):
        risk.historical_var(p, apres(p), window=20, level=1.0)
    q = p.copy()
    q.iloc[4] = np.nan
    with pytest.raises(MissingDataError):
        risk.historical_cvar(q, apres(q), window=20)


# ------------------------------------------------------------------ corrélations
def _panel(retours: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame({k: depuis_rendements(v) for k, v in retours.items()})


def test_correlation_valeur_calculee_a_la_main():
    # x = (1..5) %, y = (2, 1, 4, 3, 5) % : écarts x (-2,-1,0,1,2), y (-1,-2,1,0,2) (en %)
    # somme des produits 8, sommes des carrés 10 et 10 -> corrélation 0,8
    df = _panel({"X": [0.01, 0.02, 0.03, 0.04, 0.05], "Y": [0.02, 0.01, 0.04, 0.03, 0.05]})
    c = risk.correlation_matrix(df, apres(df), window=5).value
    assert c.loc["X", "Y"] == pytest.approx(0.8, rel=1e-9)
    assert c.loc["Y", "X"] == pytest.approx(0.8, rel=1e-9)
    assert c.loc["X", "X"] == pytest.approx(1.0)


def test_correlations_parfaites():
    r = [0.01, -0.02, 0.03, 0.00, 0.02]
    df = _panel({"A": r, "B": [2 * x for x in r], "C": [-x for x in r]})
    c = risk.correlation_matrix(df, apres(df), window=5).value
    assert c.loc["A", "B"] == pytest.approx(1.0, rel=1e-9)
    assert c.loc["A", "C"] == pytest.approx(-1.0, rel=1e-9)


def test_correlation_hebdomadaire_lit_la_grille_de_5_seances():
    idx = pd.bdate_range("2024-01-02", periods=16)
    a = pd.Series(7.0, index=idx)
    b = pd.Series(9.0, index=idx)
    for pos, va, vb in zip(
        (0, 5, 10, 15),
        (100.0, 100.0 * 1.01, 100.0 * 1.01 * 1.02, 100.0 * 1.01 * 1.02 * 1.03),
        (100.0, 100.0 * 1.02, 100.0 * 1.02 * 1.01, 100.0 * 1.02 * 1.01 * 1.04),
        strict=True,
    ):
        a.iloc[pos], b.iloc[pos] = va, vb
    df = pd.DataFrame({"A": a, "B": b})
    # rendements hebdomadaires A (1, 2, 3 %), B (2, 1, 4 %) : somme des produits d'écarts 2e-4,
    # somme des carrés A 2e-4, B 0,0014 / 3
    attendu = 2e-4 / math.sqrt(2e-4 * 0.0014 / 3)
    got = risk.correlation_matrix(df, apres(df), window=3, frequency="weekly").value
    assert got.loc["A", "B"] == pytest.approx(attendu, rel=1e-9)


def test_correlation_cas_limites():
    df = _panel({"X": [0.01, 0.02, 0.03, 0.04, 0.05], "Y": [0.02, 0.01, 0.04, 0.03, 0.05]})
    with pytest.raises(InsufficientDataError):
        risk.correlation_matrix(df, apres(df), window=20)
    nan = df.copy()
    nan.iloc[3, 1] = np.nan
    with pytest.raises(MissingDataError):
        risk.correlation_matrix(nan, apres(nan), window=5)
    plat = df.copy()
    plat["Z"] = 100.0  # rendements constants : corrélation non définie
    with pytest.raises(DegenerateSeriesError):
        risk.correlation_matrix(plat, apres(plat), window=5)


# ------------------------------------------------------------------ régime de volatilité
PARAMS = {"vol_window": 3, "history_weeks": 4, "min_weeks": 4}


def prix_regime(x_cur: float, xs: list[float], n_prices: int = 30) -> pd.Series:
    """Rendements nuls sauf, à la position L - 5k (k = 0 : courant), la fenêtre (0, +x, -x) dont
    l'écart-type d'échantillon vaut exactement x : volatilité annualisée = x x racine de 252."""
    n_ret = n_prices - 1
    r = np.zeros(n_ret)
    for k, x in enumerate([x_cur, *xs]):
        j = n_ret - 1 - 5 * k
        r[j], r[j - 1] = -x, x
    return depuis_rendements(r)


REF = [0.01, 0.02, 0.03, 0.04]  # distribution de référence : centile 50 = 0,025, centile 80 = 0,034


def test_regime_haut_au_dessus_du_centile_80():
    p = prix_regime(0.05, REF)
    res = risk.volatility_regime(p, apres(p), **PARAMS).value
    assert res.regime == "haut"
    assert res.volatility == pytest.approx(0.05 * SQ252, rel=1e-9)
    assert res.p_low == pytest.approx(0.025 * SQ252, rel=1e-9)  # numpy, interpolation linéaire
    assert res.p_high == pytest.approx(0.034 * SQ252, rel=1e-9)  # indice 2,4 : 0,03 + 0,4 x 0,01
    assert res.percentile_rank == 1.0
    assert res.n_weeks == 4
    assert res.changed is None  # pas de régime précédent


def test_regime_zone_intermediaire_hysteresis():
    p = prix_regime(0.031, REF)  # entre le centile 50 (0,025) et le centile 80 (0,034)
    t = apres(p)
    sans = risk.volatility_regime(p, t, **PARAMS).value
    assert sans.regime == "normal" and sans.percentile_rank == pytest.approx(0.75)
    assert risk.volatility_regime(p, t, previous="normal", **PARAMS).value.regime == "normal"
    garde = risk.volatility_regime(p, t, previous="haut", **PARAMS).value
    assert garde.regime == "haut" and garde.changed is False


def test_regime_retour_a_normal_sous_le_centile_50():
    p = prix_regime(0.02, REF)  # 0,02 < 0,025
    res = risk.volatility_regime(p, apres(p), previous="haut", **PARAMS).value
    assert res.regime == "normal" and res.changed is True


def test_regime_rejeu_reproduit_l_etat_sans_etat_externe():
    # semaine précédente : 0,06 > centile 80 de (0,01 ; 0,02 ; 0,03 ; 0,04) -> haut ;
    # cette semaine : 0,031 entre les deux centiles de (0,06 ; 0,01 ; 0,02 ; 0,03) -> reste haut
    p = prix_regime(0.031, [0.06, 0.01, 0.02, 0.03, 0.04], n_prices=40)
    t = apres(p)
    assert risk.volatility_regime(p, t, **PARAMS).value.regime == "normal"
    rejeu = risk.volatility_regime(p, t, replay_weeks=1, **PARAMS).value
    assert rejeu.regime == "haut" and rejeu.changed is False
    with pytest.raises(ValueError):
        risk.volatility_regime(p, t, previous="haut", replay_weeks=1, **PARAMS)


def test_regime_parametres_par_defaut_156_semaines():
    p = marche_aleatoire(1000)
    res = risk.volatility_regime(p, apres(p)).value
    assert res.n_weeks == 156
    assert res.regime in ("normal", "haut")


def test_regime_historique_insuffisant_erreur_explicite():
    p = marche_aleatoire(500)  # moins de 104 valeurs hebdomadaires de référence
    with pytest.raises(InsufficientDataError):
        risk.volatility_regime(p, apres(p))
    q = prix_regime(0.05, REF)
    q.iloc[-3] = np.nan
    with pytest.raises(MissingDataError):
        risk.volatility_regime(q, apres(q), **PARAMS)


def test_regime_centiles_invalides():
    p = prix_regime(0.05, REF)
    with pytest.raises(ValueError):
        risk.volatility_regime(p, apres(p), low_pct=80, high_pct=50, **PARAMS)


# ------------------------------------------------------------------ alertes
TH = risk.RiskThresholds(vol_window=3, history_weeks=4, min_weeks=4, drawdown_window=10)


def _actifs() -> pd.DataFrame:
    a = prix_regime(0.05, REF)  # volatilité courante au-dessus de toute la distribution
    b = serie([100.0] * 30)  # plat : volatilité nulle partout, aucun creux
    c = serie([100.0] * 26 + [88.0] * 4)  # creux de 12 % hors des fenêtres de volatilité
    d = pd.Series(np.nan, index=a.index)
    d.iloc[-10:] = 100.0  # historique trop court
    return pd.DataFrame({"A": a, "B": b, "C": c, "D": d})


def _vix(t, valeur=30.0, age=3, dispo=2) -> pd.DataFrame:
    d = pd.Timestamp(t) - timedelta(days=age)
    return pd.DataFrame(
        {
            "date": [d],
            "value": [valeur],
            "available_from": [pd.Timestamp(t) - timedelta(days=dispo)],
        }
    )


def test_alertes_par_seuils_calculees_en_python():
    df = _actifs()
    t = apres(df)
    res = risk.risk_report(df, df["A"], t, TH, vix=_vix(t)).value
    assert res.alertes["A"] == "elevee"  # rang centile 1,0 >= 0,95
    assert res.alertes["B"] == "aucune"  # rang 0,5 (série plate), creux nul
    assert res.alertes["C"] == "moderee"  # creux 88 / 100 - 1 = -12 % entre 10 % et 20 %
    assert res.indicateurs["creux_courant:C"] == pytest.approx(-0.12)
    assert res.indicateurs["vol_rang:B"] == 0.5
    assert res.indicateurs["vol_rang:A"] == 1.0
    assert "D" not in res.alertes and "D" in res.indisponibles  # jamais « aucune » par défaut
    assert res.regime_volatilite == "haut"
    assert res.alerte_marche == "moderee"  # VIX 30 entre 25 et 35
    assert res.indicateurs["vix"] == 30.0
    assert res.seuils["drawdown_high"] == 0.20


def test_alerte_vix_elevee_et_vix_perime():
    df = _actifs()
    t = apres(df)
    assert risk.risk_report(df, df["A"], t, TH, vix=_vix(t, 40.0)).value.alerte_marche == "elevee"
    perime = risk.risk_report(df, df["A"], t, TH, vix=_vix(t, 40.0, age=30, dispo=29)).value
    assert perime.alerte_marche is None and "__vix__" in perime.indisponibles


def test_regime_du_benchmark_indisponible_est_signale():
    df = _actifs()
    res = risk.risk_report(df, df["D"], apres(df), TH).value
    assert res.regime_volatilite is None and "__regime__" in res.indisponibles


def test_alertes_non_fuite_sur_prix_et_vix():
    df = _actifs()
    t = apres(df)
    vix = _vix(t)
    ref = risk.risk_report(df, df["A"], t, TH, vix=vix)
    futur_idx = pd.DatetimeIndex([pd.Timestamp(t) + timedelta(days=k) for k in range(0, 4)])
    futur = pd.DataFrame(1e6, index=futur_idx, columns=df.columns)
    ext = pd.concat([df, futur])
    vix_ext = pd.concat(
        [
            vix,
            # observation du jour t (non connue) et observation antérieure publiée après t
            pd.DataFrame(
                {
                    "date": [pd.Timestamp(t), pd.Timestamp(t) - timedelta(days=1)],
                    "value": [99.0, 99.0],
                    "available_from": [pd.Timestamp(t), pd.Timestamp(t) + timedelta(days=5)],
                }
            ),
        ]
    )
    out = risk.risk_report(ext, ext["A"], t, TH, vix=vix_ext)
    assert out.value == ref.value
    assert out.meta == ref.meta
    # changer une donnée antérieure change la sortie
    mod = df.copy()
    mod.iloc[-1, mod.columns.get_loc("B")] = 120.0
    chg = risk.risk_report(mod, mod["A"], t, TH, vix=vix).value
    assert chg.alertes["B"] != ref.value.alertes["B"] or chg.indicateurs != ref.value.indicateurs


def test_seuils_valides_et_lisibles_depuis_un_mapping():
    th = risk.RiskThresholds.from_mapping({"drawdown_moderate": 0.05, "drawdown_high": 0.3})
    assert th.drawdown_moderate == 0.05
    with pytest.raises(ValueError):
        risk.RiskThresholds.from_mapping({"inconnu": 1.0})
    with pytest.raises(ValueError):
        risk.RiskThresholds(drawdown_moderate=0.3, drawdown_high=0.1)
    with pytest.raises(ValueError):
        risk.RiskThresholds(vix_moderate=40.0, vix_high=30.0)


@pytest.mark.parametrize(("bas", "niveau"), [(91.0, "aucune"), (89.0, "moderee"), (79.0, "elevee")])
def test_seuils_de_creux_de_part_et_d_autre(bas, niveau):
    df = pd.DataFrame({"E": serie([100.0] * 26 + [bas] * 4)})
    assert risk.risk_report(df, df["E"], apres(df), TH).value.alertes["E"] == niveau


# ------------------------------------------------------------------ facteur h
def test_facteur_h_de_la_regle_l1_6_4():
    assert risk.confidence_factor_h("aucune") == 1.0
    assert risk.confidence_factor_h("moderee") == 0.8
    assert risk.confidence_factor_h("elevee") == 0.6
    assert risk.confidence_factor_h("elevee", {"elevee": 0.5, "aucune": 1.0}) == 0.5
    with pytest.raises(ToolError):
        risk.confidence_factor_h("critique")
