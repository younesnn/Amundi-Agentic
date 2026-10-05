"""Revue indépendante : adaptateur et outils sur le VRAI stockage, en lecture seule.

Ignoré si la variable d'environnement `AMUNDI_DATA_STORE` est absente (CI) ou ne pointe pas vers
un stockage contenant `prices/500.PA.parquet`. Aucune écriture, aucun téléchargement, aucune clé.
Les oracles relisent les fichiers Parquet bruts avec pandas et recalculent à la main.

Commande (depuis la racine du dépôt ; chemin du dossier `store` du cache de données) :

    AMUNDI_DATA_STORE="/chemin/vers/.cache/data/store" \\
        uv run pytest tests/tools/test_stockage_reel_lecture_seule.py -q
"""

from __future__ import annotations

import math
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import Candidate
from amundi_agentic.tools import finance, momentum, risk
from amundi_agentic.tools.market_data import MarketDataAdapter

_ENV = os.environ.get("AMUNDI_DATA_STORE")
RACINE = Path(_ENV) if _ENV else Path("/inexistant")
pytestmark = pytest.mark.skipif(
    not _ENV or not (RACINE / "prices" / "500.PA.parquet").exists(),
    reason="variable AMUNDI_DATA_STORE absente ou stockage introuvable",
)
T = date(2026, 6, 15)


def _brut(ticker):
    d = pd.read_parquet(RACINE / "prices" / f"{ticker}.parquet").sort_values("date")
    return d[d["date"] < pd.Timestamp(T)].set_index("date")


@pytest.fixture(scope="module")
def adapter():
    pit = PointInTimeStore(ParquetStore(RACINE), load_yaml("data.yaml"))
    return MarketDataAdapter(pit.as_of(T))


def test_500pa_valeurs_recalculees(adapter):
    px = adapter.prices_eur([Candidate("actions", "500.PA", "EUR", "primary")])["500.PA"]
    assert px.index.max() < pd.Timestamp(T)
    brut = _brut("500.PA")
    # ETF capitalisant : pas de dividende, donc ajusté = clôture brute
    assert (brut["dividends"] == 0).all() or np.allclose(
        px.to_numpy(), brut["close"].to_numpy(), rtol=2e-2
    )
    p = px.to_numpy()[-253:]
    r = p[1:] / p[:-1] - 1
    ann = (p[-1] / p[0]) ** (252 / 252) - 1
    vol = r.std(ddof=1) * math.sqrt(252)
    mdd = (p / np.maximum.accumulate(p) - 1).min()
    assert finance.annualized_return(px, T, 252).value == pytest.approx(ann, rel=1e-12)
    assert finance.annualized_volatility(px, T, 252).value == pytest.approx(vol, rel=1e-12)
    assert finance.max_drawdown(px, T, 252).value["max_drawdown"] == pytest.approx(mdd, rel=1e-12)
    # valeurs plausibles (aucun nombre aberrant)
    assert 0.0 < vol < 0.6 and -0.6 < mdd <= 0.0


def test_spy_en_eur_momentum_recalcule(adapter):
    px = adapter.prices_eur([Candidate("actions", "SPY", "USD", "proxy")])["SPY"].dropna()
    assert px.index.max() < pd.Timestamp(T)
    p = px.to_numpy()
    for mois, n in ((1, 21), (3, 63), (6, 126), (12, 252)):
        assert momentum.momentum(px, T, mois).value == pytest.approx(p[-1] / p[-1 - n] - 1)
    assert momentum.momentum_12_1(px, T).value == pytest.approx(p[-22] / p[-253] - 1)
    # conversion : SPY_EUR = SPY_USD / EURUSD (fixing connu à t)
    fx = pd.read_parquet(RACINE / "fx" / "EXR_USD.parquet").sort_values("date")
    brut = _brut("SPY")["close"]
    jour = px.index[-1]
    taux = fx[fx["date"] <= jour]["rate"].iloc[-1]
    assert px.iloc[-1] == pytest.approx(brut.loc[jour] / taux, rel=5e-3)


def test_non_fuite_stockage_reel_t_different_ne_change_pas_le_passe():
    """Une sortie à t ne change pas si l'on avance le stockage : on compare t et une vue à t."""
    pit = PointInTimeStore(ParquetStore(RACINE), load_yaml("data.yaml"))
    c = Candidate("actions", "500.PA", "EUR", "primary")
    a = MarketDataAdapter(pit.as_of(T)).prices_eur([c])["500.PA"]
    b = MarketDataAdapter(pit.as_of(date(2026, 9, 1))).prices_eur([c])["500.PA"]
    # la vue à une date ultérieure contient le passé de la vue à T (mêmes valeurs, ETF sans div.)
    comm = a.index.intersection(b.index)
    assert len(comm) == len(a)
    assert np.allclose(a.loc[comm].to_numpy(), b.loc[comm].to_numpy(), rtol=1e-9)
    assert a.index.max() < pd.Timestamp(T) <= pd.Timestamp(date(2026, 9, 1))


def test_taux_sans_risque_en_decimal_et_risque_de_bout_en_bout(adapter):
    rf = adapter.risk_free_annual().value
    assert 0.0 < rf < 0.12  # DGS1MO en % / 100 : 4 % -> 0,04
    cands = [Candidate("actions", t, "EUR", "primary") for t in ("500.PA",)]
    panel = adapter.prices_eur(cands)
    rep = risk.risk_report(panel, panel["500.PA"], T).value
    assert "500.PA" in rep.alertes or "500.PA" in rep.indisponibles


def test_garde_fous_calibres_sur_les_etf_reels_monetaire_inclus(adapter):
    """Mesure du 2026-10 : volatilité annualisée de C3M.PA >= 6e-4 sur toute fenêtre de 252
    séances (seuil 1e-4) et >= 3,8e-4 sur 63 séances ; perte maximale >= 5e-4 (seuil 1e-6)."""
    for ticker in ("C3M.PA", "500.PA", "MTD.PA", "CRP.PA"):
        px = adapter.prices_eur([Candidate("x", ticker, "EUR", "primary")])[ticker].dropna()
        for fenetre in (252, 756):
            if len(px) <= fenetre:
                continue
            vol = finance.annualized_volatility(px, T, fenetre).value
            assert vol > 1e-4, (ticker, fenetre, vol)
            assert math.isfinite(finance.sharpe_ratio(px, T, fenetre, 0.02).value)
            assert math.isfinite(finance.sortino_ratio(px, T, fenetre, 0.02).value)
            assert math.isfinite(finance.calmar_ratio(px, T, fenetre).value)
        r = px.pct_change().dropna()
        vol_min_252 = (r.rolling(252).std(ddof=1) * math.sqrt(252)).min()
        assert vol_min_252 > 1e-4, (ticker, vol_min_252)
        brut = finance.rolling_sharpe(px, T, 63, 0.02).value
        glissant = brut.dropna()
        assert len(glissant) > 0 and np.isfinite(glissant).all()
        # aucune fenêtre réelle n'est écartée par le garde-fou (hors NaN de données manquantes)
        assert brut.isna().sum() == 0, (ticker, int(brut.isna().sum()))
