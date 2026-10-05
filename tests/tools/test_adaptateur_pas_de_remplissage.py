"""Revue indépendante : l'adaptateur ne comble jamais un trou de prix ou de change."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from data_helpers import prix

from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import Candidate
from amundi_agentic.tools.market_data import MarketDataAdapter

DATES = pd.bdate_range("2024-01-02", "2024-03-29")


def _pit(tmp_path, retire=None, fx_jusqua=None) -> PointInTimeStore:
    store = ParquetStore(tmp_path / "store")
    n = len(DATES)
    px = prix(DATES, [100.0 + i for i in range(n)])
    if retire is not None:
        px = px[~px["date"].isin(retire)]
    store.write("prices/AAA", px)
    store.write("prices/BBB", prix(DATES, [125.0 + 1.25 * i for i in range(n)]))
    fx_dates = DATES if fx_jusqua is None else DATES[pd.Timestamp(fx_jusqua) >= DATES]
    store.write("fx/EXR_USD", pd.DataFrame({"date": fx_dates, "rate": [1.25] * len(fx_dates)}))
    return PointInTimeStore(store, load_yaml("data.yaml"))


def test_trou_de_prix_reste_nan_pas_de_remplissage(tmp_path):
    trou = [DATES[40], DATES[41]]
    pit = _pit(tmp_path, retire=trou)
    ad = MarketDataAdapter(pit.as_of(date(2024, 3, 29)))
    px = ad.prices_eur(
        [Candidate("a", "AAA", "EUR", "primary"), Candidate("b", "BBB", "USD", "proxy")]
    )
    assert px.loc[trou, "AAA"].isna().all()
    assert px["BBB"].notna().all()


def test_change_trop_ancien_donne_nan_et_est_compte(tmp_path):
    pit = _pit(tmp_path, fx_jusqua="2024-01-31")
    ad = MarketDataAdapter(pit.as_of(date(2024, 3, 29)), max_stale_days=5)
    px = ad.prices_eur([Candidate("b", "BBB", "USD", "proxy")])["BBB"]
    assert px.iloc[-1] != px.iloc[-1]  # NaN : le fixing de janvier n'est pas reporté à fin mars
    assert ad.fx_counts["BBB"]["no_fixing_nan"] > 0


def test_adaptateur_future_exclue_meme_si_stockage_contient_apres_t(tmp_path):
    pit = _pit(tmp_path)
    ad = MarketDataAdapter(pit.as_of(date(2024, 2, 15)))
    px = ad.prices_eur([Candidate("a", "AAA", "EUR", "primary")])
    assert px.index.max() == pd.Timestamp("2024-02-14")
    assert ad.as_of == date(2024, 2, 15)
    with pytest.raises(KeyError):
        MarketDataAdapter(pit.as_of(date(2024, 2, 15))).prices_eur(
            [Candidate("z", "ZZZ", "EUR", "primary")]
        )
