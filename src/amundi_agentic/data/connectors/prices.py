"""Prix ETF et actions via yfinance (sans clé).

Limites : yfinance n'est pas une API officielle de Yahoo (usage personnel, pas de redistribution),
les clôtures sont ajustées des splits à la date du téléchargement (le recalage point-in-time est
fait dans `pit.py`) ; Yahoo corrige aussi ses historiques de façon rétroactive sans en garder
trace (N9) : un retraitement n'est détecté qu'au recouvrement de la mise à jour, une correction
ancienne reste invisible ; les barres du jour courant sont écartées (incomplètes) et aucun trou n'est
comblé : les jours sans cotation restent absents.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from amundi_agentic.data.store import ParquetStore

log = logging.getLogger(__name__)

COLUMNS = ["open", "high", "low", "close", "volume", "dividends", "splits"]
Fetcher = Callable[[str, date, date], tuple[pd.DataFrame, dict]]


class NoDataError(RuntimeError):
    """Le fournisseur ne connaît pas le ticker ou ne renvoie aucune ligne."""


def yfinance_fetcher(ticker: str, start: date, end: date) -> tuple[pd.DataFrame, dict]:
    """Appel réel à yfinance (la vérification TLS reste celle de la bibliothèque)."""
    import yfinance as yf

    yf.config.debug.hide_exceptions = False  # lever les erreurs (quota, réseau) pour le backoff
    tk = yf.Ticker(ticker)
    df = tk.history(
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=False,
        actions=True,
    )
    meta = dict(tk.history_metadata or {})
    return df, meta


def normalize(df: pd.DataFrame, today: date) -> tuple[pd.DataFrame, dict[str, int]]:
    """Colonnes minuscules, index en date, écarte la barre du jour et les clôtures nulles."""
    stats = {"rows_raw": len(df), "dropped_today": 0, "dropped_null_close": 0}
    if df.empty:
        return pd.DataFrame(columns=["date", *COLUMNS]), stats
    out = df.copy()
    out.columns = [str(c).lower().replace(" ", "_") for c in out.columns]
    out = out.rename(columns={"stock_splits": "splits"})
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)  # date locale de la place (déjà celle de la cotation)
    out.index = idx.normalize()
    out.index.name = "date"
    for c in COLUMNS:
        if c not in out:
            out[c] = 0.0 if c in ("dividends", "splits") else float("nan")
    out = out[COLUMNS].reset_index()
    avant = len(out)
    out = out[out["date"] < pd.Timestamp(today)]
    stats["dropped_today"] = avant - len(out)
    avant = len(out)
    out = out[out["close"].notna()]
    stats["dropped_null_close"] = avant - len(out)
    out[["dividends", "splits"]] = out[["dividends", "splits"]].fillna(0.0)
    return out.reset_index(drop=True), stats


class PricesConnector:
    def __init__(
        self,
        store: ParquetStore,
        cfg: dict,
        cache_dir: Path,
        *,
        fetcher: Fetcher = yfinance_fetcher,
        sleep: Callable[[float], None] = time.sleep,
        today: date | None = None,
    ) -> None:
        self.store = store
        self.cfg = cfg
        self.cache_dir = Path(cache_dir) / "yfinance"
        self.fetcher = fetcher
        self._sleep = sleep
        self.today = today or datetime.now(ZoneInfo("Europe/Paris")).date()
        self._last = 0.0
        self.network_calls = 0

    # ------------------------------------------------------------------ cache disque
    def _cache_paths(self, ticker: str, start: date, end: date) -> tuple[Path, Path]:
        cle = hashlib.sha256(f"{ticker}|{start}|{end}".encode()).hexdigest()
        return self.cache_dir / f"{cle}.parquet", self.cache_dir / f"{cle}.json"

    def _fetch_cached(self, ticker: str, start: date, end: date) -> tuple[pd.DataFrame, dict]:
        donnees, meta = self._cache_paths(ticker, start, end)
        if donnees.is_file() and meta.is_file():
            return pd.read_parquet(donnees), json.loads(meta.read_text(encoding="utf-8"))
        http = self.cfg["http"]
        pause = http["sources"]["yfinance"]["min_interval_s"]
        derniere = "inconnue"
        for tentative in range(http["max_attempts"]):
            attente = pause - (time.monotonic() - self._last)
            if attente > 0:
                self._sleep(attente)
            self._last = time.monotonic()
            self.network_calls += 1
            try:
                df, info = self.fetcher(ticker, start, end)
            except Exception as exc:  # noqa: BLE001 - yfinance lève des types variés
                derniere = f"{type(exc).__name__}: {exc}"
                texte = derniere.lower()
                if "no data found" in texte or "delisted" in texte or "not found" in texte:
                    raise NoDataError(derniere) from None
                if tentative < http["max_attempts"] - 1:
                    delai = min(http["base_backoff_s"] * 2**tentative, http["max_backoff_s"])
                    log.warning(
                        "yfinance %s : %s ; nouvel essai dans %.0f s", ticker, derniere, delai
                    )
                    self._sleep(delai)
                continue
            if df is None or df.empty:
                raise NoDataError("réponse vide")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            df.reset_index().to_parquet(donnees, index=False)
            meta.write_text(json.dumps(info, default=str), encoding="utf-8")
            return df, info
        raise RuntimeError(f"yfinance {ticker} : échec après essais ({derniere})")

    # ------------------------------------------------------------------ mise à jour
    def update(self, ticker: str, *, full: bool = False) -> dict:
        """Télécharge ou met à jour un ticker. Retourne un résumé (jamais de secret)."""
        dataset = f"prices/{ticker}"
        existant = self.store.read(dataset)
        debut_total = date.fromisoformat(self.cfg["prices"]["history_start"])
        restated = False
        if existant is None or existant.empty or full:
            debut = debut_total
        else:
            dernier = existant["date"].max().date()
            debut = dernier - timedelta(days=self.cfg["prices"]["overlap_days"])
        df_brut, meta = self._fetch_cached(ticker, debut, self.today)
        neuf, stats = normalize(self._reset(df_brut), self.today)
        if existant is not None and not existant.empty and not full:
            commun = existant.merge(neuf, on="date", suffixes=("_old", "_new"))
            if not commun.empty:
                ecart = ((commun["close_new"] / commun["close_old"]) - 1).abs().max()
                if ecart > 1e-6:  # retraitement (split, dividende) : l'historique entier change
                    restated = True
                    df_brut, meta = self._fetch_cached(ticker, debut_total, self.today)
                    neuf, stats = normalize(self._reset(df_brut), self.today)
                    existant = None
        if existant is None or restated:
            self.store.write(dataset, neuf)
            nouvelles = len(neuf)
        else:
            nouvelles = self.store.upsert(dataset, neuf, ["date"])
        self.store.snapshot("prices", ticker, neuf)  # données brutes reçues, append-only
        self._write_meta(ticker, meta)
        resume = {"ticker": ticker, "new_rows": nouvelles, "restated": restated, **stats}
        self.store.log_event(
            "prices", ticker, "ok", f"restated={restated} new={nouvelles} {json.dumps(stats)}"
        )
        return resume

    @staticmethod
    def _reset(df: pd.DataFrame) -> pd.DataFrame:
        """Remet l'index de dates (le cache écrit l'index en colonne)."""
        if not isinstance(df.index, pd.DatetimeIndex):
            premiere = df.columns[0]
            df = df.set_index(premiere)
        return df

    def _write_meta(self, ticker: str, meta: dict) -> None:
        ftd = meta.get("firstTradeDate")
        if isinstance(ftd, int | float):
            ftd = datetime.fromtimestamp(ftd, UTC).date().isoformat()
        elif ftd is not None:
            ftd = str(pd.Timestamp(ftd).date())
        ligne = pd.DataFrame(
            [
                {
                    "ticker": ticker,
                    "currency": meta.get("currency"),
                    "exchange": meta.get("exchangeName"),
                    "instrument_type": meta.get("instrumentType"),
                    "long_name": meta.get("longName") or meta.get("shortName"),
                    "first_trade_date": ftd,
                    "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            ]
        )
        self.store.upsert("prices/_meta", ligne, ["ticker"])
