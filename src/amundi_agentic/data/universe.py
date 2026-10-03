"""Univers (config/universe.yaml), conversion en EUR, jonctions, monétaire capitalisé, pool de titres.

Aucune donnée n'est inventée ni interpolée : une conversion sans fixing assez récent donne NaN et
est comptée ; une jonction publie sa date, sa période de recouvrement et son écart de suivi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

import numpy as np
import pandas as pd

from amundi_agentic.data.http import HttpClient
from amundi_agentic.data.settings import load_yaml


@dataclass(frozen=True)
class Candidate:
    asset_class: str
    ticker: str
    currency: str
    role: str  # primary, proxy, alternative, control
    expected_name: str | None = None
    distribution: str = "a_verifier"  # acc, dist ou a_verifier


@dataclass(frozen=True)
class AssetClassSpec:
    name: str
    primary: Candidate
    proxy: Candidate | None
    alternatives: tuple[Candidate, ...]
    eur_series: tuple[str, ...] = field(default_factory=tuple)
    eur_series_total_return: bool = False


@dataclass(frozen=True)
class Universe:
    reference_currency: str
    min_history_weeks: int
    classes: dict[str, AssetClassSpec]
    control: tuple[Candidate, ...]
    stock_demo_tickers: tuple[str, ...]
    stock_pool: dict
    replication_cutoff: str
    paper_named_ticker: str

    @classmethod
    def load(cls) -> Universe:
        raw = load_yaml("universe.yaml")
        classes: dict[str, AssetClassSpec] = {}
        for nom, spec in raw["asset_classes"].items():
            p = spec["primary"]
            primaire = Candidate(
                nom, p["ticker"], p["currency"], "primary", p.get("expected_name"),
                p.get("distribution", "a_verifier"),
            )  # fmt: skip
            proxy = spec.get("proxy")
            classes[nom] = AssetClassSpec(
                name=nom,
                primary=primaire,
                proxy=Candidate(
                    nom,
                    proxy["ticker"],
                    proxy["currency"],
                    "proxy",
                    distribution=proxy.get("distribution", "a_verifier"),
                )
                if proxy
                else None,  # fmt: skip
                alternatives=tuple(
                    Candidate(
                        nom,
                        a["ticker"],
                        a["currency"],
                        "alternative",
                        distribution=a.get("distribution", "a_verifier"),
                    )  # fmt: skip
                    for a in spec.get("alternatives", [])
                ),
                eur_series=tuple(spec.get("eur_series", [])),
                eur_series_total_return=bool(spec.get("eur_series_total_return", False)),
            )
        controle = []
        for nom, c in raw.get("control", {}).items():
            controle.append(
                Candidate(nom, c["ticker"], c["currency"], "control",
                          distribution=c.get("distribution", "a_verifier"))
            )  # fmt: skip
            for px in c.get("proxies", []):
                controle.append(
                    Candidate(nom, px, "USD", "proxy",
                              distribution=c.get("proxies_distribution", "a_verifier"))
                )  # fmt: skip
        st = raw["stocks"]
        return cls(
            reference_currency=raw["reference_currency"],
            min_history_weeks=raw["min_history_weeks"],
            classes=classes,
            control=tuple(controle),
            stock_demo_tickers=tuple(st["demo_tickers"]),
            stock_pool=st["pool"],
            replication_cutoff=st["replication_cutoff"],
            paper_named_ticker=st["paper_named_ticker"],
        )

    def candidates(self) -> list[Candidate]:
        sortie: list[Candidate] = []
        for c in self.classes.values():
            sortie.append(c.primary)
            if c.proxy:
                sortie.append(c.proxy)
            sortie.extend(c.alternatives)
        sortie.extend(self.control)
        vus: set[str] = set()
        return [c for c in sortie if not (c.ticker in vus or vus.add(c.ticker))]

    def etf_tickers(self) -> list[str]:
        return [c.ticker for c in self.candidates()]


# ---------------------------------------------------------------------- conversion et jonction
def convert_to_eur(
    prices: pd.Series, fx: pd.Series, max_stale_days: int
) -> tuple[pd.Series, dict[str, int]]:
    """Prix en devise -> EUR au fixing BCE du jour, sinon au dernier fixing de moins de N jours.

    `fx` : unités de devise par EUR. Retour : (série en EUR, comptes). Les dates sans fixing assez
    récent donnent NaN (jamais de cours inventé). Aucun fixing postérieur à la date n'est utilisé.
    """
    gauche = prices.rename("px").to_frame().sort_index()
    droite = fx.rename("fx").to_frame().sort_index()
    gauche.index = pd.DatetimeIndex(gauche.index).astype("datetime64[ns]")
    droite.index = pd.DatetimeIndex(droite.index).astype("datetime64[ns]")
    droite["fx_date"] = droite.index
    m = pd.merge_asof(
        gauche, droite, left_index=True, right_index=True, direction="backward",
        tolerance=pd.Timedelta(days=max_stale_days),
    )  # fmt: skip
    exact = int((m["fx_date"] == m.index).sum())
    report = int(((m["fx_date"] != m.index) & m["fx"].notna()).sum())
    sans = int(m["fx"].isna().sum())
    eur = (m["px"] / m["fx"]).rename(prices.name)
    return eur, {"exact_fixing": exact, "stale_fixing_carried": report, "no_fixing_nan": sans}


@dataclass(frozen=True)
class Splice:
    series: pd.Series  # indice chaîné (base 100 à la première date de la série la plus ancienne)
    junction_date: pd.Timestamp  # première date de la série principale
    overlap_days: int
    tracking_error_annualized: float | None  # écart-type annualisé des écarts de rendement
    note: str


def splice_series(primary: pd.Series, proxy: pd.Series, min_overlap: int = 20) -> Splice:
    """Chaîne les rendements du proxy avant la première date de `primary`, ceux de `primary` après.

    Les deux séries doivent être dans la même devise (EUR). Pas d'interpolation : la jonction
    est un enchaînement de rendements. L'écart de suivi est mesuré sur la période commune.
    """
    primary, proxy = primary.dropna().sort_index(), proxy.dropna().sort_index()
    jonction = primary.index[0]
    commun = primary.index.intersection(proxy.index)
    te, note = None, "recouvrement insuffisant : écart de suivi non calculé"
    if len(commun) > min_overlap:
        rp = primary.loc[commun].pct_change().dropna()
        rx = proxy.loc[commun].pct_change().dropna()
        te = float((rp - rx).std() * np.sqrt(252))
        note = f"écart de suivi mesuré sur {len(commun)} jours communs"
    avant = proxy[proxy.index < jonction]
    if avant.empty:
        base = primary / primary.iloc[0] * 100
        return Splice(base, jonction, len(commun), te, note + " ; aucun historique proxy antérieur")
    if jonction in proxy.index:
        ancre = proxy.loc[jonction]
    else:  # pas de cours proxy à la date de jonction : on ancre sur la dernière date connue avant
        ancre = avant.iloc[-1]
        note += " ; ancrage sur la dernière cotation proxy antérieure à la jonction"
    partie_proxy = avant / ancre
    partie_primaire = primary / primary.iloc[0]
    chaine = pd.concat([partie_proxy, partie_primaire]) * 100
    return Splice(chaine, jonction, len(commun), te, note)


def money_market_index(
    eonia: pd.Series, estr: pd.Series, splice_date: str = "2019-10-01"
) -> pd.Series:
    """Indice monétaire capitalisé ACT/360 : EONIA jusqu'à la veille de `splice_date`, €STR ensuite.

    Le taux de la date d est appliqué de d à la date de taux suivante (taux en % annuel). Les jours
    sans taux ne sont pas comblés : le calcul saute d'une date de taux à la suivante.
    """
    t0 = pd.Timestamp(splice_date)
    taux = pd.concat([eonia[eonia.index < t0], estr[estr.index >= t0]]).sort_index()
    taux = taux[~taux.index.duplicated(keep="last")]
    jours = taux.index.to_series().diff().shift(-1).dt.days
    facteurs = 1 + taux / 100 * jours / 360
    facteurs = facteurs.iloc[:-1]
    indice = 100 * facteurs.cumprod()
    indice.index = taux.index[1:]
    return indice.rename("money_market_index")


# ---------------------------------------------------------------------- pool de titres daté
class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append([])
        elif tag == "tr" and self._depth == 1:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table":
            self._depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_constituents_html(html: str, sector: str) -> list[str]:
    """Symboles du premier tableau ayant les colonnes Symbol et GICS Sector, filtrés sur le secteur."""
    p = _Tables()
    p.feed(html)
    for table in p.tables:
        if not table:
            continue
        en_tete = table[0]
        if "Symbol" in en_tete and "GICS Sector" in en_tete:
            i, j = en_tete.index("Symbol"), en_tete.index("GICS Sector")
            return sorted(
                {r[i].replace(".", "-") for r in table[1:] if len(r) > max(i, j) and r[j] == sector}
            )
    return []


def fetch_stock_pool(client: HttpClient, pool_cfg: dict) -> tuple[list[str], dict]:
    """Pool daté : révision Wikipédia de la page à la date `as_of`. Retourne (symboles, métadonnées).

    LIMITE (N6) : la liste est celle de janvier 2024, donc construite avec la connaissance de 2024
    (les entrées reflètent des succès passés) ; le biais du survivant est plus fort que le seul
    constat de deux titres sans données (radiés). Les prix et dépôts viennent de sources
    « courantes » qui omettent les sociétés disparues. À contrôler en phase 7.
    """
    api = "https://en.wikipedia.org/w/api.php"
    hdr = {"User-Agent": "amundi-agentic-research/0.1 (academic prototype)"}
    rev = client.get(
        "wikipedia", api, headers=hdr,
        params={"action": "query", "prop": "revisions", "titles": pool_cfg["page"],
                "rvlimit": 1, "rvdir": "older", "rvstart": f"{pool_cfg['as_of']}T23:59:59Z",
                "rvprop": "ids|timestamp", "format": "json", "formatversion": 2},
    ).json()  # fmt: skip
    page = rev["query"]["pages"][0]
    r = page["revisions"][0]
    html = client.get(
        "wikipedia", api, headers=hdr,
        params={"action": "parse", "oldid": r["revid"], "prop": "text", "format": "json",
                "formatversion": 2},
    ).json()["parse"]["text"]  # fmt: skip
    symboles = parse_constituents_html(html, pool_cfg["sector"])
    return symboles, {"revid": r["revid"], "revision_timestamp": r["timestamp"]}
