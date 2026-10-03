"""Orchestration du téléchargement : reprise après interruption, erreurs isolées par élément.

Un élément en échec (réseau, quota, ticker inconnu) est journalisé (message expurgé de secrets) et
n'arrête pas le lot ; le résumé retourné et le rapport de couverture le signalent. Les éléments déjà
traités le même jour sont ignorés à la relance (points de reprise) ; le cache disque évite de
rappeler une requête identique.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime

import pandas as pd

from amundi_agentic.data.connectors import make_http_client
from amundi_agentic.data.connectors.esg import EsgConnector
from amundi_agentic.data.connectors.filings import FilingsConnector
from amundi_agentic.data.connectors.fx import FxConnector
from amundi_agentic.data.connectors.macro import EcbConnector, FredConnector
from amundi_agentic.data.connectors.news import NewsConnector
from amundi_agentic.data.connectors.prices import PricesConnector
from amundi_agentic.data.http import redact
from amundi_agentic.data.settings import DataSettings, load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import Universe, fetch_stock_pool

log = logging.getLogger(__name__)
SOURCES = ("prices", "fx", "macro", "filings", "news", "esg", "pool")
_SUFFIXES = re.compile(r"[,.]?\s+(inc|corp|corporation|ltd|co|plc|holdings|company)\b\.?", re.I)


def company_query(name: str) -> str:
    """Nom de société -> requête GDELT entre guillemets (suffixes juridiques retirés)."""
    return '"' + _SUFFIXES.sub("", name).strip(" ,.") + '"'


def _guard(store: ParquetStore, summary: dict, source: str, item: str, fn):
    try:
        res = fn()
        summary.setdefault(source, {"ok": 0, "error": 0, "errors": []})["ok"] += 1
        return res
    except Exception as exc:  # noqa: BLE001 - un échec ne doit pas arrêter le lot
        msg = redact(f"{type(exc).__name__}: {exc}")
        store.log_event(source, item, "error", msg)
        s = summary.setdefault(source, {"ok": 0, "error": 0, "errors": []})
        s["error"] += 1
        s["errors"].append(f"{item}: {msg[:200]}")
        log.warning("%s %s : %s", source, item, msg)
        return None


def run_fetch(
    settings: DataSettings,
    sources: list[str],
    *,
    stock_tickers: list[str] | None = None,
    etf_tickers: list[str] | None = None,
    since: str | None = None,
    gdelt_weeks: int = 0,
    resume: bool = True,
) -> dict:
    cfg = settings.config
    store = ParquetStore(settings.store_dir, settings.snapshot_dir)
    client = make_http_client(settings)
    uni = Universe.load()
    esg_cfg = load_yaml("esg.yaml")
    stocks = stock_tickers if stock_tickers is not None else list(uni.stock_demo_tickers)
    etfs = etf_tickers if etf_tickers is not None else uni.etf_tickers()
    summary: dict = {}
    today = datetime.now(UTC).date().isoformat()

    def faire(job: str, item: str, source: str, fn):
        """Exécute `fn` sauf si déjà fait aujourd'hui (reprise)."""
        cle = f"{job}-{today}"
        if resume and item in store.done_items(cle):
            summary.setdefault(source, {"ok": 0, "error": 0, "errors": []}).setdefault("skipped", 0)
            summary[source]["skipped"] += 1
            return None
        res = _guard(store, summary, source, item, fn)
        if res is not None:
            store.mark_done(cle, item)
        return res

    if "pool" in sources:

        def _pool():
            symboles, meta = fetch_stock_pool(client, uni.stock_pool)
            store.write(
                "universe/pool",
                pd.DataFrame({"ticker": symboles, **{k: str(v) for k, v in meta.items()}}),
            )
            return {"n": len(symboles)}

        faire("pool", "sp500_it_2024-01", "pool", _pool)

    pool = store.read("universe/pool")
    pool_tickers = [] if pool is None else list(pool["ticker"])

    if "prices" in sources:
        px = PricesConnector(store, cfg, settings.cache_dir)
        for tk in dict.fromkeys(etfs + stocks + (pool_tickers if "pool" in sources else [])):
            faire("prices", tk, "prices", lambda tk=tk: px.update(tk))

    if "fx" in sources:
        fx = FxConnector(client, store, cfg)
        for ccy in cfg["ecb"]["fx_currencies"]:
            faire("fx", ccy, "fx", lambda ccy=ccy: fx.fetch_currency(ccy))

    if "macro" in sources:
        fred, ecb = FredConnector(client, store, cfg), EcbConnector(client, store, cfg)
        for sid in cfg["fred"]["series"]:
            faire("fred", sid, "fred", lambda sid=sid: fred.fetch_series(sid))
        for name in cfg["ecb"]["series"]:
            faire("ecb", name, "ecb", lambda name=name: ecb.fetch_series(name))

    if "filings" in sources:
        fil = FilingsConnector(client, store, cfg)
        for tk in dict.fromkeys(stocks):
            faire("edgar_idx", tk, "edgar", lambda tk=tk: fil.fetch_filings(tk))
            faire("edgar_xbrl", tk, "xbrl", lambda tk=tk: fil.fetch_xbrl(tk))
            faire(
                "edgar_text",
                tk,
                "edgar_text",
                lambda tk=tk: fil.fetch_texts(tk, since=since or cfg["edgar"]["text_since"]),
            )
        for tk in pool_tickers:  # pool : index seulement, pour compter les titres utilisables
            faire("edgar_idx", tk, "edgar", lambda tk=tk: fil.fetch_filings(tk))

    if "news" in sources:
        nw = NewsConnector(client, store, cfg)
        for feed in cfg["news"]["feeds"]:
            faire("rss", feed["name"], "rss", lambda f=feed: nw.fetch_feed(f["name"], f["url"]))
        profils = store.read("filings/_companies")
        noms = (
            {} if profils is None else dict(zip(profils["ticker"], profils["name"], strict=False))
        )
        for tk in stocks:
            alias = cfg["news"].get("aliases", {}).get(tk)
            nom = alias or noms.get(tk)
            if nom:
                q = alias if alias else company_query(nom)
                faire("gdelt", tk, "gdelt", lambda q=q, tk=tk: nw.fetch_gdelt(q, tk))
        faire("gdelt_probe", "depth", "gdelt", lambda: nw.probe_depth())
        if gdelt_weeks:
            for tk in stocks:
                nom = cfg["news"].get("aliases", {}).get(tk) or noms.get(tk)
                if not nom:
                    continue
                q = cfg["news"].get("aliases", {}).get(tk) or company_query(nom)
                for k in range(gdelt_weeks):
                    faire(
                        "gdelt_week",
                        f"{tk}:{k}",
                        "gdelt_week",
                        lambda q=q, tk=tk, k=k: nw.backfill_week(q, tk, k),
                    )

    if "esg" in sources:
        es = EsgConnector(store, esg_cfg)
        for tk in stocks:
            faire("esg", tk, "esg", lambda tk=tk: (time.sleep(1.5), es.update_stock(tk))[1])
        for tk in etfs:
            if tk in {
                c.ticker
                for c in uni.candidates()
                if c.role in ("primary", "alternative", "control")
            }:
                faire("esg", tk, "esg", lambda tk=tk: es.update_etf(tk))
    try:
        from amundi_agentic.data.manifest import write_manifest

        write_manifest(settings)  # data_manifest.json à chaque exécution
    except OSError as exc:  # pragma: no cover
        log.warning("manifeste non écrit : %s", exc)
    return summary
