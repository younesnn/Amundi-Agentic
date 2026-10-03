"""SEC EDGAR : liste des dépôts (date d'acceptation), texte des 10-K et 10-Q, faits XBRL.

Limites d'usage (https://www.sec.gov/os/accessing-edgar-data) : User-Agent identifiant le demandeur
(variable SEC_EDGAR_USER_AGENT) et au plus 10 requêtes par seconde ; la config fixe ~6 requêtes/s.
Données publiques, sans clé. Seules les sociétés qui déposent à la SEC sont couvertes.

CONSTAT DU 2026-10-02 (revu par le reviewer-tester) : le champ `acceptanceDateTime` de l'API
`submissions` est suffixé « Z » mais sa sémantique varie selon le déposant, comparée à la page
d'index (heure de New York) : AAPL = « heure de New York + 2 x décalage » (4 h de retard sur le
vrai UTC en été, 5 h en hiver), MSFT et NVDA = vrai UTC, JPM = écart variable. Lire la valeur brute
comme UTC (`raw_as_utc`, DÉFAUT) n'est jamais antérieur à l'instant réel dans ces régimes : prudent
(service parfois retardé de quelques heures, jamais trop tôt). Une correction qui retranche 4 à 5 h
servirait les vrais UTC AVANT leur acceptation : elle a été supprimée.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import pandas as pd

from amundi_agentic.data.http import HttpClient
from amundi_agentic.data.settings import require_secret
from amundi_agentic.data.store import ParquetStore

NEW_YORK = ZoneInfo("America/New_York")
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TICKERS = "https://www.sec.gov/files/company_tickers.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"


# ---------------------------------------------------------------------- fuseaux horaires
def ny_local_to_utc(naive: datetime) -> pd.Timestamp:
    """Heure de New York (sans fuseau) -> UTC. Règle de D-023 pour un horodatage en heure locale."""
    return pd.Timestamp(naive.replace(tzinfo=NEW_YORK).astimezone(UTC))


def edgar_acceptance_to_utc(raw: str, mode: str = "raw_as_utc") -> pd.Timestamp:
    """Horodatage `acceptanceDateTime` de l'API submissions lu comme UTC (règle prudente).

    Seul le mode `raw_as_utc` existe : toute autre valeur lève ValueError (le mode « corrigé »,
    faux pour les déposants en vrai UTC, a été supprimé).
    """
    if mode != "raw_as_utc":
        raise ValueError(f"mode d'acceptation inconnu ou supprimé : {mode}")
    naif = datetime.strptime(raw.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S")
    return pd.Timestamp(naif.replace(tzinfo=UTC))


# ---------------------------------------------------------------------- analyse (fonctions pures)
def parse_company_tickers(payload: dict) -> dict[str, int]:
    return {v["ticker"].upper(): int(v["cik_str"]) for v in payload.values()}


def _rows_from_columns(cols: dict) -> list[dict]:
    n = len(cols.get("accessionNumber", []))
    return [{k: (v[i] if i < len(v) else None) for k, v in cols.items()} for i in range(n)]


def parse_filings(
    rows: list[dict], ticker: str, cik: int, forms: set[str], mode: str = "raw_as_utc"
) -> pd.DataFrame:
    sortie = []
    for r in rows:
        if r.get("form") not in forms or not r.get("acceptanceDateTime"):
            continue  # pas d'instant d'acceptation : jamais servi (aucune date inventée)
        sortie.append(
            {
                "ticker": ticker,
                "cik": cik,
                "accession": r["accessionNumber"],
                "form": r["form"],
                "filing_date": pd.Timestamp(r["filingDate"]),
                "accepted_utc": edgar_acceptance_to_utc(r["acceptanceDateTime"], mode),
                "acceptance_raw": r["acceptanceDateTime"],
                "report_date": pd.Timestamp(r["reportDate"]) if r.get("reportDate") else pd.NaT,
                "primary_document": r.get("primaryDocument") or "",
                "items": r.get("items") or "",
            }
        )
    cols = [
        "ticker", "cik", "accession", "form", "filing_date", "accepted_utc",
        "acceptance_raw", "report_date", "primary_document", "items",
    ]  # fmt: skip
    df = pd.DataFrame(sortie, columns=cols)
    return df.drop_duplicates("accession").sort_values("accepted_utc").reset_index(drop=True)


def parse_company_facts(payload: dict, concepts: list[str]) -> pd.DataFrame:
    lignes = []
    for concept in concepts:
        bloc = payload.get("facts", {}).get("us-gaap", {}).get(concept)
        if not bloc:
            continue
        for unite, faits in bloc.get("units", {}).items():
            for f in faits:
                lignes.append(
                    {
                        "concept": concept,
                        "unit": unite,
                        "start": f.get("start"),
                        "end": f.get("end"),
                        "value": f.get("val"),
                        "accn": f.get("accn"),
                        "fy": f.get("fy"),
                        "fp": f.get("fp"),
                        "form": f.get("form"),
                        "filed": f.get("filed"),
                    }
                )
    df = pd.DataFrame(
        lignes,
        columns=["concept", "unit", "start", "end", "value", "accn", "fy", "fp", "form", "filed"],
    )
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df.dropna(subset=["filed", "end"]).drop_duplicates().reset_index(drop=True)


class _TextExtractor(HTMLParser):
    BLOCS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "ix:header"):
            self._skip += 1
        elif tag in self.BLOCS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "ix:header"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    texte = "".join(p.parts).replace("\xa0", " ")
    texte = re.sub(r"[ \t]+", " ", texte)
    return re.sub(r"\n\s*\n+", "\n\n", texte).strip()


# ---------------------------------------------------------------------- connecteur
class FilingsConnector:
    def __init__(self, client: HttpClient, store: ParquetStore, cfg: dict) -> None:
        self.client = client
        self.store = store
        self.cfg = cfg
        self.mode = cfg["point_in_time"]["edgar_acceptance_mode"]
        self._ciks: dict[str, int] | None = None

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": require_secret(self.cfg["edgar"]["user_agent_env"])}

    def _get(self, url: str, ttl_s: float | None = None):
        return self.client.get("edgar", url, headers=self._headers(), ttl_s=ttl_s)

    def cik(self, ticker: str) -> int:
        if self._ciks is None:
            self._ciks = parse_company_tickers(self._get(TICKERS, ttl_s=7 * 86400).json())
        try:
            return self._ciks[ticker.upper()]
        except KeyError:
            raise KeyError(
                f"ticker {ticker} absent de la liste EDGAR (société non déclarante ?)"
            ) from None

    def fetch_filings(self, ticker: str) -> dict:
        cik = self.cik(ticker)
        soumission = self._get(SUBMISSIONS.format(cik=cik), ttl_s=86400).json()
        lignes = _rows_from_columns(soumission["filings"]["recent"])
        for extra in soumission["filings"].get("files", []):
            url = f"https://data.sec.gov/submissions/{extra['name']}"
            lignes += _rows_from_columns(self._get(url, ttl_s=86400).json())
        forms = set(self.cfg["edgar"]["forms"])
        df = parse_filings(lignes, ticker.upper(), cik, forms, self.mode)
        self.store.write(f"filings/index/{ticker.upper()}", df)
        self.store.snapshot("filings", f"index/{ticker.upper()}", df)
        profil = pd.DataFrame(
            [
                {
                    "ticker": ticker.upper(),
                    "cik": cik,
                    "name": soumission.get("name"),
                    "sic": soumission.get("sic"),
                    "sic_description": soumission.get("sicDescription"),
                    "exchanges": ",".join(soumission.get("exchanges") or []),
                    "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            ]
        )
        self.store.upsert("filings/_companies", profil, ["ticker"])
        self.store.log_event("edgar", ticker.upper(), "ok", f"filings={len(df)}")
        return {"ticker": ticker.upper(), "filings": len(df)}

    def fetch_texts(self, ticker: str, since: str | None = None) -> dict:
        """Télécharge le texte des 10-K et 10-Q (reprise : les textes déjà stockés sont ignorés)."""
        idx = self.store.read(f"filings/index/{ticker.upper()}")
        if idx is None:
            raise RuntimeError(f"index des dépôts absent pour {ticker} : lancer fetch_filings")
        formes = set(self.cfg["edgar"]["text_forms"])
        sel = idx[idx["form"].isin(formes)]
        if since:
            sel = sel[sel["filing_date"] >= pd.Timestamp(since)]
        nouveaux = deja = 0
        for ligne in sel.itertuples():
            rel = f"filings/text/{ticker.upper()}/{ligne.accession}"
            if self.store.has_text(rel):
                deja += 1
                continue
            if not ligne.primary_document:
                continue
            url = ARCHIVE.format(
                cik=ligne.cik, acc=ligne.accession.replace("-", ""), doc=ligne.primary_document
            )
            texte = html_to_text(self._get(url).text)
            self.store.write_text(rel, texte)
            nouveaux += 1
        self.store.log_event("edgar_text", ticker.upper(), "ok", f"new={nouveaux} already={deja}")
        return {"ticker": ticker.upper(), "new_texts": nouveaux, "already": deja}

    def fetch_xbrl(self, ticker: str) -> dict:
        cik = self.cik(ticker)
        payload = self._get(FACTS.format(cik=cik), ttl_s=86400).json()
        df = parse_company_facts(payload, self.cfg["edgar"]["xbrl_concepts"])
        self.store.write(f"xbrl/{ticker.upper()}", df)
        self.store.snapshot("xbrl", ticker.upper(), df)
        self.store.log_event("xbrl", ticker.upper(), "ok", f"facts={len(df)}")
        return {"ticker": ticker.upper(), "facts": len(df)}


def reindex_acceptance(store: ParquetStore, mode: str) -> int:
    """Recalcule `accepted_utc` de tous les index depuis `acceptance_raw` (sans réseau)."""
    n = 0
    for ds in store.datasets("filings/index"):
        df = store.read(ds)
        if df is None or df.empty:
            continue
        df["accepted_utc"] = [edgar_acceptance_to_utc(r, mode) for r in df["acceptance_raw"]]
        df["accepted_utc"] = pd.to_datetime(df["accepted_utc"], utc=True)
        store.write(ds, df)
        n += len(df)
    return n
