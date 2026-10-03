"""Orchestration : reprise après interruption, erreurs isolées, secrets expurgés des journaux."""

from __future__ import annotations

import pytest

from amundi_agentic.data import pipeline
from amundi_agentic.data.settings import DataSettings
from amundi_agentic.data.store import ParquetStore


class FauxPrix:
    appels: list[str] = []
    echec: set[str] = set()

    def __init__(self, store, cfg, cache_dir):
        pass

    def update(self, ticker):
        FauxPrix.appels.append(ticker)
        if ticker in FauxPrix.echec:
            raise RuntimeError("panne sur https://x?api_key=CLEPIPELINE123")
        return {"ticker": ticker}


@pytest.fixture(autouse=True)
def _faux(monkeypatch):
    FauxPrix.appels, FauxPrix.echec = [], set()
    monkeypatch.setattr(pipeline, "PricesConnector", FauxPrix)
    monkeypatch.setenv("FRED_API_KEY", "CLEPIPELINE123")


def test_erreur_isolee_et_secret_expurge(tmp_path):
    FauxPrix.echec = {"BBB"}
    s = DataSettings.load(tmp_path)
    res = pipeline.run_fetch(s, ["prices"], stock_tickers=["AAA", "BBB", "CCC"], etf_tickers=[])
    assert res["prices"]["ok"] == 2 and res["prices"]["error"] == 1  # le lot continue
    assert "CLEPIPELINE123" not in str(res)
    journal = (s.store_dir / "_status" / "events.jsonl").read_text()
    assert "CLEPIPELINE123" not in journal and '"status": "error"' in journal


def test_reprise_apres_interruption_ne_refait_que_l_echec(tmp_path):
    FauxPrix.echec = {"BBB"}
    s = DataSettings.load(tmp_path)
    pipeline.run_fetch(s, ["prices"], stock_tickers=["AAA", "BBB", "CCC"], etf_tickers=[])
    FauxPrix.appels.clear()
    FauxPrix.echec = set()  # la panne est résolue
    res = pipeline.run_fetch(s, ["prices"], stock_tickers=["AAA", "BBB", "CCC"], etf_tickers=[])
    assert FauxPrix.appels == ["BBB"]  # AAA et CCC repris du point de reprise
    assert res["prices"]["skipped"] == 2 and res["prices"]["ok"] == 1
    assert ParquetStore(s.store_dir).done_items(
        next(iter((s.store_dir / "_jobs").glob("prices-*"))).stem
    ) == {"AAA", "BBB", "CCC"}


def test_sans_reprise_tout_est_rejoue(tmp_path):
    s = DataSettings.load(tmp_path)
    pipeline.run_fetch(s, ["prices"], stock_tickers=["AAA"], etf_tickers=[])
    FauxPrix.appels.clear()
    pipeline.run_fetch(s, ["prices"], stock_tickers=["AAA"], etf_tickers=[], resume=False)
    assert FauxPrix.appels == ["AAA"]
