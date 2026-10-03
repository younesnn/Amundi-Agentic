"""ESG : exclusions par secteur (code SIC EDGAR) et scores gratuits disponibles.

Sources gratuites : code SIC de l'émetteur (EDGAR), indicateurs et score de risque ESG exposés par
yfinance (Sustainalytics via Yahoo, sans historique ni garantie de service), méthodologie d'indice
des ETF (config/esg.yaml). Aucune de ces données n'est historisée : chaque collecte est un
instantané daté (`observed_at`), servi en point-in-time seulement après sa date de collecte.
Limite : le SIC est une approximation d'activité (un fabricant d'ordinateurs et un fabricant de
munitions n'ont pas le même SIC, mais un code ne mesure pas la part de chiffre d'affaires).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from amundi_agentic.data.store import ParquetStore

log = logging.getLogger(__name__)
VendorFetcher = Callable[[str], dict | None]
COLS = [
    "asset_id", "kind", "score", "score_source", "exclusions", "exclusion_basis", "determined",
    "observed_at", "sic", "notes",
]  # fmt: skip


def yfinance_sustainability(ticker: str) -> dict | None:
    """Score et indicateurs d'implication de yfinance ; None si le fournisseur n'a rien."""
    import yfinance as yf

    df = yf.Ticker(ticker).sustainability
    if df is None or getattr(df, "empty", True):
        return None
    serie = df.iloc[:, 0]
    return {str(k): v for k, v in serie.to_dict().items()}


def sic_exclusions(sic: int | str | None, rules: dict) -> list[str]:
    """Catégories d'exclusion dont un intervalle SIC contient `sic` (règles `enforce: false` incluses)."""
    if sic in (None, "") or pd.isna(sic):
        return []
    code = int(sic)
    return [
        nom for nom, r in rules.items() if any(a <= code <= b for a, b in r.get("sic_ranges", []))
    ]


def enforced(categories: list[str], rules: dict) -> list[str]:
    return [c for c in categories if rules[c].get("enforce", True)]


class EsgConnector:
    def __init__(
        self,
        store: ParquetStore,
        esg_cfg: dict,
        *,
        vendor: VendorFetcher = yfinance_sustainability,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.store = store
        self.cfg = esg_cfg
        self.vendor = vendor
        self.now = now

    def _save(self, ligne: dict) -> None:
        df = pd.DataFrame([ligne], columns=COLS)
        self.store.upsert("esg/records", df, ["asset_id", "observed_at"])
        self.store.snapshot("esg", ligne["asset_id"], df)

    def update_stock(self, ticker: str) -> dict:
        regles = self.cfg["normative_exclusions"]
        profils = self.store.read("filings/_companies")
        sic = None
        if profils is not None and (profils["ticker"] == ticker).any():
            sic = profils.loc[profils["ticker"] == ticker, "sic"].iloc[0]
            sic = None if sic is None or pd.isna(sic) else str(sic)
        notes: list[str] = []
        try:
            fournisseur = self.vendor(ticker)
        except Exception as exc:  # noqa: BLE001 - service gratuit instable
            fournisseur = None
            notes.append(f"vendor_error:{type(exc).__name__}")
        score = None
        from_vendor: list[str] = []
        if fournisseur:
            brut = fournisseur.get("totalEsg")
            score = float(brut) if brut is not None and not pd.isna(brut) else None
            for nom, r in regles.items():
                flag = fournisseur.get(r.get("vendor_flag", ""))
                if flag is not None:
                    notes.append(f"vendor_flag:{nom}")  # critère déterminé par donnée
                if flag is True:
                    from_vendor.append(nom)
        else:
            notes.append("no_vendor_score")
        par_secteur = sic_exclusions(sic, regles)
        if sic in (None, ""):
            notes.append("no_sic")
        toutes = sorted(set(par_secteur) | set(from_vendor))
        retenues = enforced(toutes, regles)
        base = "sic+vendor_flag" if from_vendor else ("sic" if sic not in (None, "") else None)
        ligne = {
            "asset_id": ticker,
            "kind": "stock",
            "score": score,
            "score_source": self.cfg["score"]["vendor"] if score is not None else None,
            "exclusions": "|".join(retenues),
            "exclusion_basis": base,
            "determined": base is not None,
            "observed_at": pd.Timestamp(self.now()),
            "sic": None if sic in (None, "") else str(sic),
            "notes": "|".join(notes),
        }
        self._save(ligne)
        self.store.log_event("esg", ticker, "ok", f"score={score is not None} excl={len(retenues)}")
        return ligne

    def update_etf(self, ticker: str) -> dict:
        meth = self.cfg["etf_methodology"]
        spec = meth["by_ticker"].get(ticker, meth["default"])
        defn = self.cfg["basis_definitions"][spec["basis"]]
        determiné = defn.get("determined", True)
        notes = [f"basis:{spec['basis']}", "verified" if spec.get("verified") else "not_verified"]
        ligne = {
            "asset_id": ticker,
            "kind": "etf",
            "score": None,
            "score_source": None,
            "exclusions": "|".join(defn["exclusions"]),
            "exclusion_basis": "etf_methodology" if determiné else None,
            "determined": determiné,
            "observed_at": pd.Timestamp(self.now()),
            "sic": None,
            "notes": "|".join(notes),
        }
        self._save(ligne)
        self.store.log_event("esg", ticker, "ok", f"etf basis={spec['basis']}")
        return ligne
