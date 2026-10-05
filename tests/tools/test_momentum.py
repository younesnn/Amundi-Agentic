"""tools/momentum.py : momentum, tendance, synthèse, contre des valeurs calculées à la main.

Série de référence : P_i = 100 + i pour i = 0..259 (260 clôtures), dernière clôture 359.
"""

from __future__ import annotations

import numpy as np
import pytest
from tools_helpers import apres, serie

from amundi_agentic.tools import momentum
from amundi_agentic.tools.base import InsufficientDataError, MissingDataError

P = serie([100 + i for i in range(260)])
T = apres(P)


@pytest.mark.parametrize(
    ("mois", "attendu"),
    [
        (1, 359 / 338 - 1),  # 359 / (359 - 21)
        (3, 359 / 296 - 1),  # 359 / (359 - 63)
        (6, 359 / 233 - 1),  # 359 / (359 - 126)
        (12, 359 / 107 - 1),  # 359 / (359 - 252)
    ],
)
def test_momentum_par_horizon(mois, attendu):
    assert momentum.momentum(P, T, mois).value == pytest.approx(attendu, rel=1e-12)


def test_momentum_12_1_saute_le_dernier_mois():
    # P(-1-21) = 338 ; P(-1-252) = 107
    assert momentum.momentum_12_1(P, T).value == pytest.approx(338 / 107 - 1, rel=1e-12)


def test_tendance_moyenne_mobile_200():
    # 200 dernières clôtures : 160 .. 359, moyenne 259,5
    res = momentum.trend_vs_sma(P, T, 200).value
    assert res["sma"] == pytest.approx(259.5)
    assert res["ecart_sma"] == pytest.approx(359 / 259.5 - 1)
    assert res["tendance"] == "haussiere"


def test_tendance_baissiere_et_neutre():
    desc = serie([300 - i for i in range(5)])
    assert momentum.trend_vs_sma(desc, apres(desc), 5).value["tendance"] == "baissiere"
    plat = serie([5, 5, 5, 5, 5])
    assert momentum.trend_vs_sma(plat, apres(plat), 5).value["tendance"] == "neutre"


def test_horizon_inconnu_refuse():
    with pytest.raises(ValueError):
        momentum.momentum(P, T, 2)


def test_serie_trop_courte_erreur_explicite():
    court = P.iloc[:100]
    with pytest.raises(InsufficientDataError):
        momentum.momentum(court, apres(court), 12)
    with pytest.raises(InsufficientDataError):
        momentum.momentum_12_1(court, apres(court))
    with pytest.raises(InsufficientDataError):
        momentum.trend_vs_sma(court, apres(court), 200)


def test_prix_manquant_a_une_borne_erreur():
    p = P.copy()
    p.iloc[-1 - 63] = np.nan
    with pytest.raises(MissingDataError):
        momentum.momentum(p, apres(p), 3)
    # les autres horizons ne sont pas touchés
    assert momentum.momentum(p, apres(p), 1).value == pytest.approx(359 / 338 - 1)


def test_synthese_calcule_ce_qui_est_possible_et_nomme_les_manquants():
    court = P.iloc[
        :100
    ]  # 100 clôtures : 1 et 3 mois possibles ; ni 6, ni 12 mois, ni 12-1, ni SMA 200
    res = momentum.valuation_summary(court, apres(court), rf_annual=0.0, window=60).value
    v, m = res["valeurs"], res["manquants"]
    # derniers prix : 100 .. 199
    assert v["momentum_1m"] == pytest.approx(199 / 178 - 1)
    assert v["momentum_3m"] == pytest.approx(199 / 136 - 1)
    assert "momentum_6m" in m  # 127 clôtures requises, 100 disponibles
    assert "momentum_12m" in m and "momentum_12_1" in m and "tendance_sma200" in m
    assert "InsufficientDataError" in m["momentum_12m"]
    assert v["rendement_annualise"] == pytest.approx((199 / 139) ** (252 / 60) - 1)
    assert v["perte_maximale"] == 0.0  # série croissante
    assert "calmar" in m  # aucune perte : ratio non défini, jamais inventé
    assert v["creux_courant"] == 0.0


def test_synthese_cite_la_derniere_date():
    res = momentum.valuation_summary(P, T, window=60)
    assert res.meta.last_data_date == P.index[-1].date()
    assert res.meta.tool == "valuation_summary"
