"""Cours de change : taux de référence BCE (EXR, quotidiens, ~14 h 15 CET).

Convention BCE : unités de devise par EUR (USD 1,10 signifie 1 EUR = 1,10 USD). Les jours sans
fixing (fériés TARGET) restent absents ; le report du dernier cours est fait explicitement, borné
et compté dans `pit.py` / `universe.py`, jamais ici.
"""

from __future__ import annotations

import pandas as pd

from amundi_agentic.data.connectors.macro import EcbConnector
from amundi_agentic.data.http import HttpClient
from amundi_agentic.data.store import ParquetStore


class FxConnector:
    def __init__(self, client: HttpClient, store: ParquetStore, cfg: dict) -> None:
        self._ecb = EcbConnector(client, store, cfg)
        self.store = store
        self.cfg = cfg

    def fetch_currency(self, currency: str) -> dict:
        df = self._ecb.fetch_csv("EXR", f"D.{currency}.EUR.SP00.A")
        out = pd.DataFrame({"date": df["date"], "rate": df["value"]})
        self.store.write(f"fx/EXR_{currency}", out)
        self.store.snapshot("fx", f"EXR_{currency}", out)
        self.store.log_event("fx", currency, "ok", f"rows={len(out)}")
        return {"currency": currency, "rows": len(out)}
