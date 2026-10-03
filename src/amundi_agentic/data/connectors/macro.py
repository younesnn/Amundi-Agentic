"""Macro : FRED avec millésimes ALFRED, et séries BCE (SDMX, sans millésimes).

FRED : tous les millésimes sont conservés (colonnes realtime_start et realtime_end), ce qui permet
de servir, à t, la valeur connue avant t. La clé API est lue dans l'environnement (FRED_API_KEY),
n'entre ni dans la clé de cache ni dans les journaux.
Limites : FRED plafonne 2000 dates de millésime par requête (on découpe la fenêtre) ; les séries
ICE BofA sont limitées par licence à une fenêtre glissante d'environ 3 ans ; un millésime ALFRED
antérieur à la capture par ALFRED n'est pas un vrai millésime (realtime_start = date de capture).
BCE : pas de millésimes ; la disponibilité est la fin de période plus un délai déclaré en config (H).
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from amundi_agentic.data.http import HttpClient, HttpError
from amundi_agentic.data.settings import require_secret
from amundi_agentic.data.store import ParquetStore

log = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
FAR_FUTURE = date(9999, 12, 31)
STILL_VALID = "2262-04-10"


# ---------------------------------------------------------------------- FRED (fonctions pures)
def parse_fred_observations(payload: dict) -> tuple[pd.DataFrame, int]:
    """Observations FRED -> DataFrame.

    Un marqueur « . » (valeur absente) devient NaN : la ligne est CONSERVÉE (une valeur peut être
    retirée par un millésime ultérieur) ; `pit.py` l'écarte au service. Le nombre est compté.
    """
    lignes = payload.get("observations", [])
    df = pd.DataFrame(lignes, columns=["date", "realtime_start", "realtime_end", "value"])
    valeurs = pd.to_numeric(df["value"].replace(".", pd.NA), errors="coerce")
    manquants = int(valeurs.isna().sum())
    df = df.assign(value=valeurs)
    # 9999-12-31 (millésime encore valide) est hors de la plage de datetime64 : sentinelle 2262-04-10
    df["realtime_end"] = df["realtime_end"].astype(str).str.replace("9999-12-31", STILL_VALID)
    for c in ("date", "realtime_start", "realtime_end"):
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.normalize()
    return df.reset_index(drop=True), manquants


def merge_vintage_chunks(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Fusionne les lignes (date, valeur) contiguës dans le temps réel, coupées par le découpage."""
    if not frames:
        return pd.DataFrame(columns=["date", "realtime_start", "realtime_end", "value"])
    df = pd.concat(frames, ignore_index=True).sort_values(["date", "realtime_start"])
    sortie: list[dict] = []
    for ligne in df.to_dict("records"):
        if sortie:
            prec = sortie[-1]
            contigu = (
                prec["date"] == ligne["date"]
                and prec["value"] == ligne["value"]
                and ligne["realtime_start"] <= prec["realtime_end"] + pd.Timedelta(days=1)
            )
            if contigu:
                prec["realtime_end"] = max(prec["realtime_end"], ligne["realtime_end"])
                continue
        sortie.append(dict(ligne))
    return pd.DataFrame(sortie)


def us_business_days(n: int) -> pd.offsets.CustomBusinessDay:
    """Jours ouvrés américains (fériés fédéraux exclus), sans dépendance nouvelle."""
    return pd.offsets.CustomBusinessDay(n, calendar=USFederalHolidayCalendar())


def add_us_business_days(dates: pd.Series, n: int) -> pd.Series:
    """`dates` + n jours ouvrés américains, vectorisé (équivalent à `dates + us_business_days(n)`)."""
    if dates.empty:
        return dates
    cal = USFederalHolidayCalendar()
    fer = cal.holidays(dates.min() - pd.Timedelta(days=10), dates.max() + pd.Timedelta(days=40))
    d = dates.values.astype("datetime64[D]")
    # roll=backward : une date non ouvrée est ramenée au jour ouvré précédent, comme pandas
    res = np.busday_offset(d, n, roll="backward", holidays=fer.values.astype("datetime64[D]"))
    return pd.Series(pd.to_datetime(res), index=dates.index)


class FredConnector:
    def __init__(self, client: HttpClient, store: ParquetStore, cfg: dict) -> None:
        self.client = client
        self.store = store
        self.cfg = cfg

    def _get(self, path: str, params: dict, ttl_s: float | None = None) -> dict:
        p = {**params, "api_key": require_secret("FRED_API_KEY"), "file_type": "json"}
        return self.client.get("fred", f"{FRED_BASE}/{path}", params=p, ttl_s=ttl_s).json()

    def _window(self, series_id: str, a: date, b: date, ttl_s: float | None) -> list[pd.DataFrame]:
        sortie: list[pd.DataFrame] = []
        offset = 0
        while True:
            params = {
                "series_id": series_id,
                "realtime_start": a.isoformat(),
                "realtime_end": b.isoformat(),
                "limit": 100000,
                "offset": offset,
            }
            try:
                payload = self._get("series/observations", params, ttl_s)
            except HttpError as exc:
                if exc.status == 400 and "vintage dates" in exc.body and (b - a).days > 1:
                    milieu = a + (b - a) // 2 if b != FAR_FUTURE else date.today()
                    return self._window(series_id, a, milieu, ttl_s) + self._window(
                        series_id, milieu + timedelta(days=1), b, ttl_s
                    )
                raise
            df, manquants = parse_fred_observations(payload)
            df.attrs["missing_markers"] = manquants
            sortie.append(df)
            offset += payload.get("limit", 100000)
            if offset >= payload.get("count", 0):
                return sortie

    def _latest(self, series_id: str) -> tuple[pd.DataFrame, int]:
        """Observations actuelles (sans millésimes), paginées."""
        morceaux, offset, manquants = [], 0, 0
        while True:
            payload = self._get(
                "series/observations",
                {"series_id": series_id, "limit": 100000, "offset": offset},
                ttl_s=86400,
            )
            df, m = parse_fred_observations(payload)
            morceaux.append(df)
            manquants += m
            offset += payload.get("limit", 100000)
            if offset >= payload.get("count", 0):
                return pd.concat(morceaux, ignore_index=True), manquants

    def fetch_series(self, series_id: str) -> dict:
        spec = self.cfg["fred"]["series"].get(series_id, {"revised": True})
        try:
            meta = self._get("series", {"series_id": series_id}, ttl_s=86400)["seriess"][0]
        except HttpError as exc:
            if exc.status == 400 and "does not exist" in exc.body:
                msg = f"série absente de FRED : {exc.body[:120]}"
                self.store.log_event("fred", series_id, "unavailable", msg)
                return {"series_id": series_id, "unavailable": True}
            raise
        manquants = 0
        if spec.get("revised", True):
            fenetres: list[tuple[date, date]] = [(date(1776, 7, 4), date(2000, 12, 31))]
            debut = date(2001, 1, 1)
            while debut <= date.today():
                fenetres.append((debut, date(debut.year + 3, 12, 31)))
                debut = date(debut.year + 4, 1, 1)
            fenetres[-1] = (fenetres[-1][0], FAR_FUTURE)  # dernière fenêtre : millésimes ouverts
            morceaux: list[pd.DataFrame] = []
            for i, (a, b) in enumerate(fenetres):
                ttl = 86400 if i == len(fenetres) - 1 else None
                try:
                    blocs = self._window(series_id, a, b, ttl)
                except HttpError as exc:
                    if exc.status == 400 and "does not exist in ALFRED" in exc.body:
                        continue  # ALFRED n'a pas de millésime sur cette fenêtre
                    raise
                for df in blocs:
                    manquants += df.attrs.get("missing_markers", 0)
                    morceaux.append(df)
            if not morceaux:
                self.store.log_event("fred", series_id, "unavailable", "aucun millésime ALFRED")
                return {"series_id": series_id, "unavailable": True}
            fusion = merge_vintage_chunks([m for m in morceaux if not m.empty])
            fusion["availability"] = "alfred"
        else:
            fusion, manquants = self._latest(series_id)
            # disponibilité par règle (H), pas un millésime : vendredi + 1 jour ouvré = lundi
            fusion["realtime_start"] = add_us_business_days(
                fusion["date"], spec.get("lag_business_days", 1)
            )
            fusion["availability"] = "lag_rule"
        self.store.write(f"macro/fred/{series_id}", fusion)
        self.store.snapshot("macro", f"fred/{series_id}", fusion)
        ligne = pd.DataFrame(
            [
                {
                    "series_id": series_id,
                    "title": meta.get("title"),
                    "units": meta.get("units"),
                    "frequency": meta.get("frequency_short"),
                    "observation_start": meta.get("observation_start"),
                    "observation_end": meta.get("observation_end"),
                    "missing_markers": manquants,
                    "availability": "alfred" if spec.get("revised", True) else "lag_rule",
                    "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            ]
        )
        self.store.upsert("macro/fred/_meta", ligne, ["series_id"])
        self.store.log_event("fred", series_id, "ok", f"rows={len(fusion)}")
        return {"series_id": series_id, "rows": len(fusion), "missing_markers": manquants}


# ---------------------------------------------------------------------- BCE
def parse_ecb_csv(texte: str) -> pd.DataFrame:
    """CSV SDMX de la BCE -> colonnes date (début de période), period_end, value."""
    df = pd.read_csv(io.StringIO(texte), usecols=["TIME_PERIOD", "OBS_VALUE"])
    df = df.rename(columns={"TIME_PERIOD": "period", "OBS_VALUE": "value"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    p = df["period"].astype(str)
    mensuel = p.str.fullmatch(r"\d{4}-\d{2}")
    debut = pd.to_datetime(p.where(~mensuel, p + "-01"), errors="coerce")
    fin = debut.where(~mensuel, debut + pd.offsets.MonthEnd(0))
    return (
        pd.DataFrame({"date": debut, "period_end": fin, "value": df["value"]})
        .dropna(subset=["date"])
        .drop_duplicates("date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )


class EcbConnector:
    def __init__(self, client: HttpClient, store: ParquetStore, cfg: dict) -> None:
        self.client = client
        self.store = store
        self.cfg = cfg

    def fetch_csv(self, flow: str, key: str, start: str = "1999-01-01") -> pd.DataFrame:
        resp = self.client.get(
            "ecb",
            f"{ECB_BASE}/{flow}/{key}",
            params={"format": "csvdata", "startPeriod": start},
            ttl_s=86400,
        )
        return parse_ecb_csv(resp.text)

    def fetch_series(self, name: str) -> dict:
        spec = self.cfg["ecb"]["series"][name]
        df = self.fetch_csv(spec["flow"], spec["key"])
        self.store.write(f"macro/ecb/{name}", df)
        self.store.snapshot("macro", f"ecb/{name}", df)
        self.store.log_event("ecb", name, "ok", f"rows={len(df)}")
        return {"series": name, "rows": len(df)}
