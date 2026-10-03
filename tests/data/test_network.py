"""Tests réseau (lancés à la main : `uv run pytest -m network`). Exclus de la CI.

Ils appellent les vraies sources gratuites ; les clés viennent de .env (jamais affichées).
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import pytest

from amundi_agentic.data.connectors import make_http_client
from amundi_agentic.data.connectors.filings import FilingsConnector, ny_local_to_utc
from amundi_agentic.data.connectors.fx import FxConnector
from amundi_agentic.data.connectors.macro import FredConnector
from amundi_agentic.data.connectors.news import NewsConnector
from amundi_agentic.data.connectors.prices import PricesConnector
from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import DataSettings, load_dotenv
from amundi_agentic.data.store import ParquetStore

pytestmark = pytest.mark.network


@pytest.fixture
def env(tmp_path):
    load_dotenv()
    s = DataSettings.load(tmp_path)
    return s, ParquetStore(s.store_dir), make_http_client(s)


def test_prix_yfinance_spy(env):
    s, st, _ = env
    r = PricesConnector(st, s.config, s.cache_dir).update("SPY")
    assert r["new_rows"] > 1000
    p = PointInTimeStore(st, s.config).as_of(date(2020, 3, 1)).prices(["SPY"])
    assert p.index.max() < pd.Timestamp("2020-03-01")


def test_fx_bce_usd(env):
    s, st, c = env
    FxConnector(c, st, s.config).fetch_currency("USD")
    assert st.read("fx/EXR_USD")["date"].min() == pd.Timestamp("1999-01-04")


def test_fred_alfred_gdpc1_millesimes(env):
    s, st, c = env
    FredConnector(c, st, s.config).fetch_series("GDPC1")
    df = st.read("macro/fred/GDPC1")
    assert df.groupby("date").size().max() > 1  # des révisions existent
    vue = PointInTimeStore(st, s.config).as_of(date(2015, 1, 1)).macro_long("fred:GDPC1")
    assert (vue["available_from"] < pd.Timestamp("2015-01-01")).all()


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA"])
def test_edgar_acceptation_coherente_avec_la_page_d_index(env, ticker):
    """Propriété qui compte : l'instant servi (raw_as_utc) n'est jamais antérieur à l'acceptation
    réelle (heure de New York de la page d'index), quel que soit le régime du déposant."""
    s, st, c = env
    fc = FilingsConnector(c, st, s.config)
    fc.fetch_filings(ticker)
    idx = st.read(f"filings/index/{ticker}")
    echantillon = idx[idx["form"].isin(["10-K", "10-Q"])].iloc[::9].head(5)
    assert len(echantillon) >= 3
    for r in echantillon.itertuples():
        url = f"https://www.sec.gov/Archives/edgar/data/{r.cik}/{r.accession.replace('-', '')}/{r.accession}-index.htm"
        html = fc._get(url).text
        m = re.search(r"Accepted</div>\s*<div[^>]*>([^<]+)<", html)
        reel = ny_local_to_utc(pd.Timestamp(m.group(1)).to_pydatetime())
        assert r.accepted_utc >= reel, (ticker, r.accession)


def test_gdelt_une_requete(env):
    s, st, c = env
    r = NewsConnector(c, st, s.config).fetch_gdelt('"Apple"', "AAPL")
    assert r["entries"] >= 0
