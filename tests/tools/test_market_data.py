"""tools/market_data.py : l'adaptateur assemble les entrées via `as_of(t)` sans refaire le PIT."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from data_helpers import prix

from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import Candidate
from amundi_agentic.tools import finance
from amundi_agentic.tools.base import MissingDataError
from amundi_agentic.tools.market_data import MarketDataAdapter

DATES = pd.bdate_range("2024-01-02", "2024-03-29")
AAA = Candidate("actions", "AAA", "EUR", "primary")
BBB = Candidate("actions", "BBB", "USD", "proxy")


@pytest.fixture
def pit(tmp_path) -> PointInTimeStore:
    store = ParquetStore(tmp_path / "store")
    n = len(DATES)
    store.write("prices/AAA", prix(DATES, [100.0 + i for i in range(n)]))
    store.write("prices/BBB", prix(DATES, [125.0 + 1.25 * i for i in range(n)]))
    store.write("fx/EXR_USD", pd.DataFrame({"date": DATES, "rate": [1.25] * n}))
    rf = pd.DataFrame(
        {
            "date": DATES,
            "realtime_start": DATES + pd.Timedelta(days=1),
            "realtime_end": pd.Timestamp("2262-04-10"),
            "value": [5.0 if d < pd.Timestamp("2024-02-01") else 4.0 for d in DATES],
        }
    )
    store.write("macro/fred/DGS1MO", rf)
    return PointInTimeStore(store, load_yaml("data.yaml"))


def test_prix_en_eur_au_cours_bce_connu(pit):
    t = date(2024, 2, 15)
    px = MarketDataAdapter(pit.as_of(t)).prices_eur([AAA, BBB])
    assert list(px.columns) == ["AAA", "BBB"]
    assert px.index.max() < pd.Timestamp(t)  # la clôture de t n'est pas servie (D-038)
    # BBB en USD / 1,25 USD par EUR = 100 + i, comme AAA
    assert px["BBB"].to_numpy() == pytest.approx(px["AAA"].to_numpy())


def test_aucune_donnee_posterieure_a_t_dans_les_entrees(pit):
    for t in (date(2024, 1, 20), date(2024, 2, 15), date(2024, 3, 29)):
        ad = MarketDataAdapter(pit.as_of(t))
        px = ad.prices_eur([AAA, BBB])
        assert px.index.max() < pd.Timestamp(t)
        macro, _ = ad.macro_series(["fred:DGS1MO"])
        assert (macro["fred:DGS1MO"]["available_from"] < pd.Timestamp(t)).all()


def test_taux_sans_risque_decimal_dernier_et_moyenne(pit):
    ad = MarketDataAdapter(pit.as_of(date(2024, 2, 15)))
    assert ad.risk_free_annual().value == pytest.approx(0.04)  # dernière valeur, 4 % -> 0,04
    # moyenne des observations de [2024-01-29, t) connues : 5 % jusqu'au 31 janvier, 4 % après
    moy = ad.risk_free_annual(window_start=date(2024, 1, 29)).value
    jours = [d for d in DATES if pd.Timestamp("2024-01-29") <= d < pd.Timestamp("2024-02-14")]
    vals = [5.0 if d < pd.Timestamp("2024-02-01") else 4.0 for d in jours]
    assert moy == pytest.approx(sum(vals) / len(vals) / 100)


def test_taux_sans_risque_sans_observation_erreur(pit):
    ad = MarketDataAdapter(pit.as_of(date(2024, 1, 2)))  # rien de connu avant le 2 janvier
    with pytest.raises(MissingDataError):
        ad.risk_free_annual()


def test_serie_absente_listee_pas_inventee(pit):
    ad = MarketDataAdapter(pit.as_of(date(2024, 2, 15)))
    macro, absentes = ad.macro_series(["fred:DGS1MO", "fred:GDPC1"])
    assert "fred:DGS1MO" in macro and "fred:GDPC1" in absentes and "fred:GDPC1" not in macro


def test_de_bout_en_bout_adaptateur_vers_outil(pit):
    t = date(2024, 2, 15)
    ad = MarketDataAdapter(pit.as_of(t))
    px = ad.prices_eur([AAA])["AAA"]
    # fenêtre de 5 rendements : 6 dernières clôtures connues (dernière : 2024-02-14)
    res = finance.cumulative_return(px, t, window=5)
    n = len(px)  # AAA vaut 100 + i, i = 0..n-1
    assert res.value == pytest.approx((100.0 + n - 1) / (100.0 + n - 6) - 1.0)
    assert res.meta.last_data_date == px.index[-1].date()
