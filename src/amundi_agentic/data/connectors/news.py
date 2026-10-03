"""News : flux RSS d'institutions et GDELT DOC 2.0.

Dates (D-023) : on sert un article à t si son instant de publication est antérieur à la coupure.
- RSS : date de publication du flux (UTC). Un article sans date valide est écarté et compté, jamais
  daté artificiellement. Un flux RSS ne contient que les articles récents : aucun historique n'est
  disponible avant la première collecte ; `first_seen_at` enregistre notre première observation.
- GDELT : `seendate` est l'instant de première observation par GDELT, pas la date de publication ;
  il est servi comme `published_at` (borne prudente) avec time_semantics = « seendate ».
Limites : GDELT demande une requête toutes les 5 s au plus (429 sinon) ; sa fenêtre de recherche
DOC est glissante (la profondeur réelle est mesurée par `probe_depth`).
GDELT : usage libre avec citation de la source ; les flux RSS restent la propriété des éditeurs
(usage de recherche, pas de redistribution).
"""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import feedparser
import pandas as pd

from amundi_agentic.data.http import HttpClient, HttpError
from amundi_agentic.data.store import ParquetStore

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
COLS = [
    "item_id", "source", "published_at", "first_seen_at", "title", "summary", "url",
    "time_semantics", "tags",
]  # fmt: skip


def _item_id(source: str, url: str, title: str) -> str:
    return hashlib.sha256(f"{source}|{url or title}".encode()).hexdigest()[:24]


def parse_rss(content: bytes, feed_name: str, seen_at: datetime) -> tuple[pd.DataFrame, dict]:
    flux = feedparser.parse(content)
    lignes, sans_date = [], 0
    for e in flux.entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not t:
            sans_date += 1
            continue
        pub = datetime.fromtimestamp(calendar.timegm(t), UTC)
        titre, url = e.get("title", ""), e.get("link", "")
        lignes.append(
            {
                "item_id": _item_id(feed_name, url, titre),
                "source": feed_name,
                "published_at": pub,
                "first_seen_at": seen_at,
                "title": titre,
                "summary": e.get("summary", ""),
                "url": url,
                "time_semantics": "published",
                "tags": "",
            }
        )
    return pd.DataFrame(lignes, columns=COLS), {"entries": len(flux.entries), "no_date": sans_date}


def parse_gdelt(payload: dict, tag: str, seen_at: datetime) -> tuple[pd.DataFrame, dict]:
    lignes, sans_date = [], 0
    arts = payload.get("articles", [])
    for a in arts:
        try:
            pub = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except (KeyError, ValueError):
            sans_date += 1
            continue
        lignes.append(
            {
                "item_id": _item_id("gdelt", a.get("url", ""), a.get("title", "")),
                "source": "gdelt",
                "published_at": pub,
                "first_seen_at": seen_at,
                "title": a.get("title", ""),
                "summary": "",
                "url": a.get("url", ""),
                "time_semantics": "seendate",
                "tags": tag,
            }
        )
    return pd.DataFrame(lignes, columns=COLS), {"entries": len(arts), "no_date": sans_date}


def _gdelt_json(resp) -> dict:
    """Corps JSON de GDELT ; un corps vide signifie « aucun résultat », un texte libre une erreur."""
    if not resp.text.strip():
        return {}
    try:
        return resp.json()
    except ValueError:
        raise HttpError(f"gdelt : réponse non JSON ({resp.text[:120]!r})") from None


def _is_json(content: bytes) -> bool:
    try:
        json.loads(content)
    except ValueError:
        return False
    return True


class NewsConnector:
    def __init__(self, client: HttpClient, store: ParquetStore, cfg: dict) -> None:
        self.client = client
        self.store = store
        self.cfg = cfg

    def _append(self, df: pd.DataFrame) -> int:
        """Ajoute les articles inconnus (les existants gardent leur `first_seen_at`)."""
        if df.empty:
            return 0
        df = df.drop_duplicates("item_id")
        self.store.snapshot("news", "items", df)  # lot reçu, avant fusion
        ancien = self.store.read("news/items")
        if ancien is not None and not ancien.empty:
            connus = df[df["item_id"].isin(ancien["item_id"])]
            for (
                ligne
            ) in connus.itertuples():  # fusion des étiquettes (un article, plusieurs actifs)
                masque = ancien["item_id"] == ligne.item_id
                tags = set(str(ancien.loc[masque, "tags"].iloc[0]).split("|")) | set(
                    str(ligne.tags).split("|")
                )
                ancien.loc[masque, "tags"] = "|".join(sorted(t for t in tags if t))
            df = df[~df["item_id"].isin(ancien["item_id"])]
            df = pd.concat([ancien, df], ignore_index=True)
            n_new = len(df) - len(ancien)
        else:
            n_new = len(df)
        self.store.write("news/items", df.sort_values("published_at").reset_index(drop=True))
        return n_new

    def fetch_feed(self, name: str, url: str) -> dict:
        resp = self.client.get(
            "rss", url, headers={"User-Agent": "amundi-agentic-research"}, ttl_s=3600
        )
        df, stats = parse_rss(resp.content, name, datetime.now(UTC))
        nouveaux = self._append(df)
        self.store.log_event("rss", name, "ok", f"{json.dumps(stats)} new={nouveaux}")
        return {"feed": name, "new": nouveaux, **stats}

    def fetch_gdelt(
        self, query: str, tag: str, start: datetime | None = None, end: datetime | None = None
    ) -> dict:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": self.cfg["news"]["gdelt"]["max_records"],
            "sort": "datedesc",
        }
        if start:
            params["startdatetime"] = start.strftime("%Y%m%d%H%M%S")
        if end:
            params["enddatetime"] = end.strftime("%Y%m%d%H%M%S")
        resp = self.client.get(
            "gdelt",
            GDELT_URL,
            params=params,
            headers={"User-Agent": "amundi-agentic-research"},
            ttl_s=None if end else 3600,
            validate=_is_json,
        )
        payload = _gdelt_json(resp)
        df, stats = parse_gdelt(payload, tag, datetime.now(UTC))
        nouveaux = self._append(df)
        self.store.log_event("gdelt", tag, "ok", f"{json.dumps(stats)} new={nouveaux}")
        return {"tag": tag, "new": nouveaux, **stats}

    def backfill_week(
        self, query: str, tag: str, weeks_ago: int, today: date | None = None
    ) -> dict:
        """Sonde une semaine (7 jours se terminant `weeks_ago` semaines avant aujourd'hui) : y a-t-il
        au moins un article GDELT pour `query` ? Les articles trouvés sont ajoutés au stock."""
        today = today or datetime.now(UTC).date()
        fin = datetime.combine(today - timedelta(weeks=weeks_ago), datetime.min.time())
        debut = fin - timedelta(days=7)
        params = {
            "query": query, "mode": "artlist", "format": "json", "sort": "datedesc",
            "maxrecords": self.cfg["news"]["gdelt"]["backfill_max_records"],
            "startdatetime": debut.strftime("%Y%m%d%H%M%S"),
            "enddatetime": fin.strftime("%Y%m%d%H%M%S"),
        }  # fmt: skip
        resp = self.client.get(
            "gdelt",
            GDELT_URL,
            params=params,
            headers={"User-Agent": "amundi-agentic-research"},
            validate=_is_json,
        )
        df, stats = parse_gdelt(_gdelt_json(resp), tag, datetime.now(UTC))
        self._append(df)
        ligne = pd.DataFrame(
            [{"tag": tag, "week_start": pd.Timestamp(debut), "week_end": pd.Timestamp(fin),
              "articles_returned": stats["entries"], "cap": params["maxrecords"]}]
        )  # fmt: skip
        self.store.upsert("news/_gdelt_weeks", ligne, ["tag", "week_start"])
        return {"tag": tag, "weeks_ago": weeks_ago, **stats}

    def probe_depth(self, today: date | None = None) -> pd.DataFrame:
        """Mesure la profondeur historique de GDELT DOC : une fenêtre de 7 jours par ancienneté."""
        today = today or datetime.now(UTC).date()
        cfg = self.cfg["news"]["gdelt"]
        lignes = []
        for mois in cfg["probe_months_back"]:
            fin = datetime.combine(today - timedelta(days=30 * mois), datetime.min.time())
            debut = fin - timedelta(days=7)
            etat, n, premier = "ok", 0, None
            try:
                params = {
                    "query": cfg["probe_query"], "mode": "artlist", "format": "json",
                    "maxrecords": 5, "startdatetime": debut.strftime("%Y%m%d%H%M%S"),
                    "enddatetime": fin.strftime("%Y%m%d%H%M%S"),
                }  # fmt: skip
                resp = self.client.get(
                    "gdelt",
                    GDELT_URL,
                    params=params,
                    headers={"User-Agent": "amundi-agentic-research"},
                    validate=_is_json,
                )
                arts = _gdelt_json(resp).get("articles", [])
                n = len(arts)
                premier = min((a["seendate"] for a in arts), default=None)
            except (HttpError, ValueError) as exc:
                etat = f"erreur: {str(exc)[:120]}"
            lignes.append(
                {"months_back": mois, "window_start": debut.date().isoformat(),
                 "window_end": fin.date().isoformat(), "articles": n,
                 "earliest_seendate": premier, "status": etat}
            )  # fmt: skip
        df = pd.DataFrame(lignes)
        self.store.write("news/_gdelt_probe", df)
        return df
