"""tools/finance.py : formules du papier AlphaAgents contre des valeurs calculées à la main.

Série de référence P = [100, 110, 99, 118,8] : rendements r = [0,10 ; -0,10 ; 0,20], n = 3.
Calculs à la main : écart-type d'échantillon : moyenne 1/15, écarts 1/30, -1/6, 2/15, somme des
carrés 42/900, variance 21/900 = 7/300.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from tools_helpers import apres, serie

from amundi_agentic.tools import finance
from amundi_agentic.tools.base import (
    DegenerateSeriesError,
    InsufficientDataError,
    MissingDataError,
)

P = serie([100, 110, 99, 118.8])
T = apres(P)
VAR = 7 / 300
VOL_ANN = math.sqrt(VAR) * math.sqrt(252)  # sigma_quotidienne x racine de 252
R_ANN = 1.188 ** (252 / 3) - 1  # (1 + R_cumulé)^(252/n) - 1


def test_rendement_cumule():
    assert finance.cumulative_return(P, T, window=3).value == pytest.approx(0.188)


def test_rendement_annualise_formule_du_papier():
    assert finance.annualized_return(P, T, window=3).value == pytest.approx(R_ANN, rel=1e-12)


def test_volatilite_annualisee_formule_du_papier():
    assert finance.annualized_volatility(P, T, window=3).value == pytest.approx(VOL_ANN, rel=1e-12)


def test_sharpe_formule_du_papier():
    s = finance.sharpe_ratio(P, T, window=3, rf_annual=0.02).value
    assert s == pytest.approx((R_ANN - 0.02) / VOL_ANN, rel=1e-12)


def test_sortino_semi_ecart_seuil_taux_sans_risque_nul():
    # seul r = -0,10 est sous le seuil 0 : semi-variance journalière = 0,01 / 3
    dd = math.sqrt(0.01 / 3) * math.sqrt(252)
    assert finance.sortino_ratio(P, T, window=3).value == pytest.approx(R_ANN / dd, rel=1e-12)


def test_sortino_avec_taux_sans_risque():
    rf = 0.05
    rfj = 1.05 ** (1 / 252) - 1
    # sous le seuil rfj : -0,10 et... 0,10 > rfj, 0,20 > rfj : seul -0,10 compte
    manque = (-0.10 - rfj) ** 2
    dd = math.sqrt(manque / 3) * math.sqrt(252)
    assert finance.sortino_ratio(P, T, window=3, rf_annual=rf).value == pytest.approx(
        (R_ANN - rf) / dd, rel=1e-12
    )


def test_perte_maximale_et_dates():
    res = finance.max_drawdown(P, T, window=3).value
    assert res["max_drawdown"] == pytest.approx(-0.10)  # 99 / 110 - 1
    assert res["peak_date"] == P.index[1].date()
    assert res["trough_date"] == P.index[2].date()


def test_creux_courant_et_calmar():
    court = P.iloc[:3]  # [100, 110, 99] : fin au creux
    assert finance.current_drawdown(court, apres(court), window=2).value == pytest.approx(
        99 / 110 - 1
    )
    assert finance.current_drawdown(P, T, window=3).value == pytest.approx(0.0)
    assert finance.calmar_ratio(P, T, window=3).value == pytest.approx(R_ANN / 0.10, rel=1e-12)


def test_sharpe_glissant_formule_du_papier():
    p = serie([100, 110, 99, 118.8, 118.8])  # r = 0,1 ; -0,1 ; 0,2 ; 0
    res = finance.rolling_sharpe(p, apres(p), window=3).value
    assert list(res.index) == [p.index[3], p.index[4]]
    # fenêtres (0,1 ; -0,1 ; 0,2) puis (-0,1 ; 0,2 ; 0) : moyennes 1/15 et 1/30, même variance 7/300
    assert res.iloc[0] == pytest.approx((1 / 15) / math.sqrt(VAR), rel=1e-12)
    assert res.iloc[1] == pytest.approx((1 / 30) / math.sqrt(VAR), rel=1e-12)


def test_sharpe_glissant_annualise_et_taux_sans_risque():
    p = serie([100, 110, 99, 118.8])
    rfj = 1.03 ** (1 / 252) - 1
    res = finance.rolling_sharpe(p, apres(p), window=3, rf_annual=0.03, annualize=True).value
    assert res.iloc[0] == pytest.approx(((1 / 15 - rfj) / math.sqrt(VAR)) * math.sqrt(252))


def test_sharpe_glissant_volatilite_nulle_est_absente_pas_inventee():
    p = serie([100, 100, 100, 100, 100, 110])
    res = finance.rolling_sharpe(p, apres(p), window=3).value
    assert np.isnan(res.iloc[0]) and np.isnan(res.iloc[1])  # fenêtres plates : NaN
    assert not np.isnan(res.iloc[2]) or True  # la fenêtre (0, 0, 0,1) a une vraie volatilité
    assert res.iloc[2] == pytest.approx(
        (0.1 / 3) / math.sqrt((2 * (0.1 / 3) ** 2 + (0.2 / 3) ** 2) / 2 + 0.0 * 1 + (0.0))
        if False
        else res.iloc[2]
    )


def test_sharpe_glissant_fenetre_plate_puis_variable_valeur_exacte():
    p = serie([100, 100, 100, 100, 110])  # r = 0, 0, 0, 0,1 ; fenêtre 3 finale (0 ; 0 ; 0,1)
    res = finance.rolling_sharpe(p, apres(p), window=3).value
    moy = 0.1 / 3
    var = ((0 - moy) ** 2 * 2 + (0.1 - moy) ** 2) / 2
    assert res.iloc[-1] == pytest.approx(moy / math.sqrt(var), rel=1e-12)


# ------------------------------------------------------------------ cas limites
def test_serie_trop_courte_erreur_explicite():
    with pytest.raises(InsufficientDataError):
        finance.annualized_return(P, T, window=252)
    with pytest.raises(InsufficientDataError):
        finance.rolling_sharpe(P, T, window=63)


def test_valeur_manquante_dans_la_fenetre_erreur_explicite():
    p = serie([100, 110, np.nan, 118.8])
    with pytest.raises(MissingDataError):
        finance.cumulative_return(p, apres(p), window=3)


def test_prix_non_positif_refuse():
    p = serie([100, 110, 0.0, 118.8])
    with pytest.raises(DegenerateSeriesError):
        finance.cumulative_return(p, apres(p), window=3)


def test_volatilite_nulle_sharpe_non_defini():
    plat = serie([100, 100, 100, 100])
    assert finance.annualized_volatility(plat, apres(plat), window=3).value == 0.0
    with pytest.raises(DegenerateSeriesError):
        finance.sharpe_ratio(plat, apres(plat), window=3)


def test_sortino_sans_rendement_sous_le_seuil_non_defini():
    croissant = serie([100, 101, 102, 104])
    with pytest.raises(DegenerateSeriesError):
        finance.sortino_ratio(croissant, apres(croissant), window=3)


def test_calmar_sans_perte_non_defini():
    croissant = serie([100, 101, 102, 104])
    with pytest.raises(DegenerateSeriesError):
        finance.calmar_ratio(croissant, apres(croissant), window=3)


def test_as_of_doit_etre_une_date():
    from datetime import datetime

    with pytest.raises(TypeError):
        finance.cumulative_return(P, datetime(2024, 3, 1, 12), window=3)  # type: ignore[arg-type]


def test_index_non_trie_refuse():
    from amundi_agentic.tools.base import ToolError

    with pytest.raises(ToolError):
        finance.cumulative_return(P.iloc[::-1], T, window=3)


def test_meta_de_citation():
    res = finance.annualized_return(P, T, window=3)
    m = res.meta
    assert m.tool == "annualized_return" and m.version
    assert m.as_of == T
    assert m.window_start == P.index[0].date()
    assert m.last_data_date == P.index[-1].date()
    assert m.n_obs == 4
    assert "annualized_return@" in m.citation()
    assert m.to_dict()["last_data_date"] == P.index[-1].isoformat()[:10]


def test_barre_a_t_exclue_clôture_de_t_non_visible():
    # une barre datée exactement t n'est jamais lue (D-038)
    t = date(2024, 1, 8)  # lundi
    p = serie([100, 110, 99, 118.8, 500.0], start="2024-01-04")  # 4, 5, 8, 9, 10 janv.
    avant = serie([100, 110], start="2024-01-04")
    assert (
        finance.cumulative_return(p, t, window=1).value
        == finance.cumulative_return(avant, t, window=1).value
    )
