"""Accès point-in-time `as_of(t)` (L1 §3.3, §11.3, D-023, EX-NF-11).

Coupure : t 00:00 heure de Paris, convertie en UTC. Tout est filtré sur « publié STRICTEMENT avant
la coupure » : une donnée publiée exactement à la coupure n'est pas servie.

| Source | Règle appliquée |
| --- | --- |
| Prix | barres dont la date de séance est < t (clôture de t-1 au plus), recalées point-in-time |
| Macro FRED | millésime ALFRED : `realtime_start` < t, dernière version connue par observation |
| Macro BCE | fin de période + délai de publication (config) < t |
| Dépôts SEC | instant d'acceptation (UTC) < coupure |
| Faits XBRL | dernier dépôt `filed` < t par (concept, unité, période) ; acceptation < coupure si connue |
| News | instant de publication (UTC) < coupure |
| ESG | instantané dont l'instant de collecte < coupure ; sinon seulement en mode `non_pit` |
| Change | date du fixing + délai < t |

Recalage des prix : Yahoo ajuste toute la série des splits (et dividendes) connus à la date du
téléchargement. À t, on ne connaît que ceux dont la date est < t : les clôtures sont multipliées par
le produit des splits de date >= t, et le facteur de dividendes n'utilise que les dividendes
détachés avant t. Le prix servi est donc celui qu'on aurait calculé à t.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from amundi_agentic.data.models import EsgRecord, Filing, LookAheadError, NewsItem, NewsQuery
from amundi_agentic.data.store import ParquetStore

PARIS = ZoneInfo("Europe/Paris")
PRICE_FIELDS = ("open", "high", "low", "close", "adj_close", "volume")


def cutoff_utc(t: date) -> pd.Timestamp:
    """Instant de coupure : t 00:00 heure de Paris, en UTC."""
    if isinstance(t, datetime):
        raise TypeError(
            "as_of attend une date (la coupure est t 00:00 Europe/Paris), pas un datetime"
        )
    return pd.Timestamp(datetime(t.year, t.month, t.day, tzinfo=PARIS).astimezone(UTC))


def pit_prices(df: pd.DataFrame, t: date) -> pd.DataFrame:
    """Barres connues à t, recalées des seuls splits et dividendes connus à t."""
    t_ts = pd.Timestamp(t)
    df = df.sort_values("date")
    connu = df[df["date"] < t_ts].copy()
    futur = df[df["date"] >= t_ts]
    facteur = float(futur.loc[futur["splits"] > 0, "splits"].prod()) if len(futur) else 1.0
    for c in ("open", "high", "low", "close"):
        connu[c] = connu[c] * facteur
    connu["volume"] = connu["volume"] / facteur
    precedent = connu["close"].shift(1)
    f = 1.0 - connu["dividends"].where(connu["dividends"] > 0, 0.0) * facteur / precedent
    f = f.where((connu["dividends"] > 0) & precedent.notna(), 1.0)
    # bar d est ajustée par les dividendes détachés APRÈS d (ligne d'indice supérieur) et avant t
    m = f[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    connu["adj_close"] = connu["close"] * m
    return connu.reset_index(drop=True)


class DataView:
    """Vue des données connues à la coupure de t. Tout accès est filtré avant retour."""

    def __init__(self, store: ParquetStore, t: date, cfg: dict, esg_mode: str = "strict") -> None:
        if esg_mode not in ("strict", "non_pit"):
            raise ValueError("esg_mode doit valoir 'strict' ou 'non_pit'")
        self._store = store
        self.t = t
        self.cutoff = cutoff_utc(t)
        self._cfg = cfg
        self._esg_mode = esg_mode
        self.last_data_date: dict[
            str, pd.Timestamp
        ] = {}  # sortie datée par la dernière donnée (EX-O1-03)

    def _note(self, cle: str, valeur) -> None:
        if valeur is not None and not pd.isna(valeur):
            self.last_data_date[cle] = pd.Timestamp(valeur)

    def _lire(self, dataset: str) -> pd.DataFrame:
        df = self._store.read(dataset)
        if df is None:
            raise KeyError(f"jeu de données absent du stockage : {dataset}")
        return df

    # ------------------------------------------------------------------ prix
    def prices(
        self, tickers: list[str], start: date | None = None, field: str = "adj_close"
    ) -> pd.DataFrame:
        if field not in PRICE_FIELDS:
            raise ValueError(f"champ inconnu : {field}")
        colonnes = {}
        for tk in tickers:
            brut = self._lire(f"prices/{tk}")
            pit = pit_prices(brut, self.t)
            if start is not None:
                pit = pit[pit["date"] >= pd.Timestamp(start)]
            s = pit.set_index("date")[field]
            colonnes[tk] = s
            if len(s):
                self._note(f"prices:{tk}", s.index.max())
        out = pd.DataFrame(
            colonnes
        ).sort_index()  # NaN là où une série n'a pas de barre : jamais comblé
        if len(out) and out.index.max() >= pd.Timestamp(self.t):
            raise LookAheadError(f"prix postérieurs à t={self.t}")
        return out

    # ------------------------------------------------------------------ macro
    def macro_long(self, series_id: str) -> pd.DataFrame:
        """Dernière version connue de chaque observation : date, value, available_from."""
        t_ts = pd.Timestamp(self.t)
        origine, nom = series_id.split(":", 1)
        if origine == "fred":
            df = self._lire(f"macro/fred/{nom}")
            df = df[df["realtime_start"] < t_ts]
            df = df.sort_values(["date", "realtime_start"]).groupby("date", as_index=False).tail(1)
            df = df.dropna(subset=["value"])
            out = df.rename(columns={"realtime_start": "available_from"})[
                ["date", "value", "available_from"]
            ]
        elif origine == "ecb":
            df = self._lire(f"macro/ecb/{nom}")
            lag = self._cfg["ecb"]["series"][nom]["lag_days"]
            dispo = df["period_end"] + pd.Timedelta(days=lag)
            df = df.assign(available_from=dispo)
            out = df[df["available_from"] < t_ts][["date", "value", "available_from"]]
        else:
            raise ValueError(f"origine macro inconnue : {origine} (attendu fred: ou ecb:)")
        out = out.sort_values("date").reset_index(drop=True)
        if len(out) and out["available_from"].max() >= t_ts:
            raise LookAheadError(f"macro {series_id} postérieure à t={self.t}")
        if len(out):
            self._note(f"macro:{series_id}", out["date"].max())
        return out

    def macro(self, series_ids: list[str], start: date | None = None) -> pd.DataFrame:
        colonnes = {}
        for sid in series_ids:
            long = self.macro_long(sid)
            if start is not None:
                long = long[long["date"] >= pd.Timestamp(start)]
            colonnes[sid] = long.set_index("date")["value"]
        return pd.DataFrame(colonnes).sort_index()

    # ------------------------------------------------------------------ dépôts SEC
    def filings(self, ticker: str, forms: set[str] | None = None) -> list[Filing]:
        idx = self._lire(f"filings/index/{ticker.upper()}")
        idx = idx[idx["accepted_utc"] < self.cutoff]
        if forms:
            idx = idx[idx["form"].isin(forms)]
        sortie = []
        for r in idx.sort_values("accepted_utc").itertuples():
            sortie.append(
                Filing(
                    ticker=r.ticker,
                    cik=str(r.cik),
                    accession=r.accession,
                    form=r.form,
                    filing_date=r.filing_date.date(),
                    accepted_utc=r.accepted_utc.to_pydatetime(),
                    report_date=None if pd.isna(r.report_date) else r.report_date.date(),
                    primary_document=r.primary_document,
                    has_text=self._store.has_text(f"filings/text/{r.ticker}/{r.accession}"),
                )
            )
        if sortie:
            self._note(f"filings:{ticker.upper()}", sortie[-1].accepted_utc)
        return sortie

    def filing_text(self, ticker: str, accession: str) -> str | None:
        idx = self._lire(f"filings/index/{ticker.upper()}")
        ligne = idx[idx["accession"] == accession]
        if ligne.empty:
            raise KeyError(f"dépôt inconnu : {accession}")
        if ligne["accepted_utc"].iloc[0] >= self.cutoff:
            raise LookAheadError(f"dépôt {accession} accepté après la coupure de t={self.t}")
        return self._store.read_text(f"filings/text/{ticker.upper()}/{accession}")

    def xbrl_facts(self, ticker: str, concepts: list[str] | None = None) -> pd.DataFrame:
        df = self._lire(f"xbrl/{ticker.upper()}")
        df = df[df["filed"] < pd.Timestamp(self.t)]
        idx = self._store.read(f"filings/index/{ticker.upper()}")
        accepte: dict = {}
        if idx is not None:  # ceinture : acceptation connue et postérieure à la coupure => exclu
            accepte = dict(zip(idx["accession"], idx["accepted_utc"], strict=False))
            tard = df["accn"].map(accepte).apply(lambda x: bool(pd.notna(x)) and x >= self.cutoff)
            df = df[~tard.fillna(False).astype(bool)]
        if concepts:
            df = df[df["concept"].isin(concepts)]
        # départage de deux dépôts du même jour : instant d'acceptation, puis accn
        df = df.assign(_accepte=df["accn"].map(accepte)).sort_values(["filed", "_accepte", "accn"])
        df = df.drop(columns="_accepte")
        cle = ["concept", "unit", "start", "end"]
        out = df.groupby(cle, dropna=False, as_index=False).tail(1)
        out = out.sort_values(cle + ["filed"]).reset_index(drop=True)
        if len(out) and out["filed"].max() >= pd.Timestamp(self.t):
            raise LookAheadError(f"faits XBRL postérieurs à t={self.t}")
        if len(out):
            self._note(f"xbrl:{ticker.upper()}", out["filed"].max())
        return out

    # ------------------------------------------------------------------ news
    def news(self, query: NewsQuery) -> list[NewsItem]:
        df = self._store.read("news/items")
        if df is None or df.empty:
            return []
        df = df[df["published_at"] < self.cutoff]
        if query.start is not None:
            df = df[df["published_at"] >= pd.Timestamp(query.start, tz="UTC")]
        if query.sources:
            df = df[df["source"].isin(query.sources)]
        if query.tags:
            df = df[df["tags"].apply(lambda s: bool(set(str(s).split("|")) & set(query.tags)))]
        if query.terms:
            texte = (df["title"].fillna("") + " " + df["summary"].fillna("")).str.lower()
            masque = pd.Series(False, index=df.index)
            for terme in query.terms:
                masque |= texte.str.contains(terme.lower(), regex=False)
            df = df[masque]
        df = df.sort_values("published_at", ascending=False)
        if query.limit:
            df = df.head(query.limit)
        if len(df) and df["published_at"].max() >= self.cutoff:
            raise LookAheadError(f"news postérieures à la coupure de t={self.t}")
        items = [
            NewsItem(
                item_id=r.item_id,
                source=r.source,
                published_at=r.published_at.to_pydatetime(),
                title=r.title,
                summary=r.summary,
                url=r.url,
                time_semantics=r.time_semantics,
                tags=tuple(x for x in str(r.tags).split("|") if x),
            )
            for r in df.itertuples()
        ]
        if items:
            self._note("news", items[0].published_at)
        return items

    # ------------------------------------------------------------------ ESG
    def esg(self, asset_id: str) -> EsgRecord | None:
        df = self._store.read("esg/records")
        if df is None:
            return None
        df = df[df["asset_id"] == asset_id].sort_values("observed_at")
        connu = df[df["observed_at"] < self.cutoff]
        if not connu.empty:
            ligne, non_pit = connu.iloc[-1], False
        elif self._esg_mode == "non_pit" and not df.empty:
            ligne, non_pit = df.iloc[-1], True  # instantané postérieur à t : non point-in-time
        else:
            return None
        sep = lambda s: tuple(x for x in str(s or "").split("|") if x)  # noqa: E731
        return EsgRecord(
            asset_id=asset_id,
            score=None if pd.isna(ligne["score"]) else float(ligne["score"]),
            score_source=ligne["score_source"] if isinstance(ligne["score_source"], str) else None,
            exclusions=sep(ligne["exclusions"]),
            exclusion_basis=ligne["exclusion_basis"]
            if isinstance(ligne["exclusion_basis"], str)
            else None,
            observed_at=ligne["observed_at"].to_pydatetime(),
            non_point_in_time=non_pit,
            notes=sep(ligne["notes"]),
        )

    # ------------------------------------------------------------------ change
    def fx_eur(self, currency: str, start: date | None = None) -> pd.Series:
        """Unités de `currency` pour 1 EUR (convention BCE), fixings connus à t."""
        df = self._lire(f"fx/EXR_{currency}")
        lag = pd.Timedelta(days=self._cfg["ecb"]["fx_lag_days"])
        df = df[(df["date"] + lag) < pd.Timestamp(self.t)]
        if start is not None:
            df = df[df["date"] >= pd.Timestamp(start)]
        s = df.set_index("date")["rate"].sort_index().rename(currency)
        if len(s):
            self._note(f"fx:{currency}", s.index.max())
        return s


class PointInTimeStore:
    def __init__(self, store: ParquetStore, cfg: dict) -> None:
        self._store = store
        self._cfg = cfg

    def as_of(self, t: date, *, esg_mode: str = "strict") -> DataView:
        cutoff_utc(t)  # valide le type
        return DataView(self._store, t, self._cfg, esg_mode)
