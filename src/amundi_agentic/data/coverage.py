"""Rapport de couverture des données, généré par script (aucun chiffre écrit à la main).

    uv run python -m amundi_agentic.data.coverage            # écrit docs/couverture_donnees.md
    uv run amundi-agentic data coverage

Tout chiffre du rapport provient du stockage local (`.cache/data/store`) ; une source absente ou en
erreur est dite telle quelle (« indisponible »), jamais remplacée par une valeur.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from amundi_agentic.data.analysis import (
    DETERMINE,
    INCONNU,
    SUPPOSE,
    composition,
    cross_check,
    drawdown_table,
    esg_matrix,
    liquidity_stats,
)
from amundi_agentic.data.models import QualityIssue
from amundi_agentic.data.pit import pit_prices
from amundi_agentic.data.quality import check_dated_series, check_duplicates, check_prices
from amundi_agentic.data.settings import ROOT, DataSettings, load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import Universe

LICENCES = {
    "yfinance": "Non officielle (Yahoo) ; usage personnel/recherche ; pas de redistribution ; instable.",
    "FRED/ALFRED": "Clé gratuite ; séries ICE BofA limitées par licence à une fenêtre glissante ; pas de redistribution des séries tierces.",
    "BCE (SDMX)": "Réutilisation libre avec mention de la source ; pas de millésimes.",
    "SEC EDGAR": "Domaine public ; User-Agent obligatoire ; 10 requêtes/s maximum.",
    "GDELT": "Libre avec citation ; 1 requête / 5 s ; fenêtre de recherche glissante.",
    "RSS": "Propriété des éditeurs ; recherche seulement ; historique nul.",
    "ESG (SIC, yfinance, méthodologie)": "SIC public ; scores Yahoo/Sustainalytics non garantis, non historisés.",
    "Wikipédia (pool)": "CC BY-SA 4.0 ; révision datée.",
}


def md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    if not rows:
        return "_aucune ligne_\n"
    cols = cols or list(rows[0])
    sortie = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        sortie.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    return "\n".join(sortie) + "\n"


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/d"
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat() if not pd.isna(v) else "n/d"
    if isinstance(v, float):
        return f"{v:.0f}" if abs(v) >= 100 else f"{v:.3g}"
    return str(v).replace("|", "/")


def _dt(v):
    return None if v is None or pd.isna(v) else pd.Timestamp(v).date().isoformat()


class Report:
    def __init__(self, settings: DataSettings) -> None:
        self.settings = settings
        self.cfg = settings.config
        self.store = ParquetStore(settings.store_dir)
        self.uni = Universe.load()
        self.esg_cfg = load_yaml("esg.yaml")
        self.q = self.cfg["quality"]
        self.issues: list[QualityIssue] = []
        self.issues_avant: list[QualityIssue] = []  # avant la fenêtre utile
        self.issues_struct: list[QualityIssue] = []  # faux positifs structurels (config)
        self.data: dict = {}
        self.sections: list[str] = []

    # ------------------------------------------------------------------ prix
    def _price_rows(self, tickers: dict[str, tuple[str, str, str | None]]) -> list[dict]:
        meta = self.store.read("prices/_meta")
        meta_by = {} if meta is None else meta.set_index("ticker").to_dict("index")
        lignes = []
        window = pd.Timestamp(self.q["window_start"])
        structural = self.q.get("structural_stale", {})
        for tk, spec in tickers.items():
            classe, role, ccy_attendue = spec[:3]
            distribution = spec[3] if len(spec) > 3 else None
            df = self.store.read(f"prices/{tk}")
            m = meta_by.get(tk, {})
            if df is None:
                lignes.append(
                    {"classe": classe, "role": role, "ticker": tk, "statut": "indisponible"}
                )
                continue
            iss_all = check_prices(
                df, tk, self.q, meta=m, expected_currency=ccy_attendue, distribution=distribution
            )
            iss = []
            avant = Counter()
            for i in iss_all:
                if i.kind == "stale" and tk in structural:
                    self.issues_struct.append(i)
                elif (
                    i.kind in ("stale", "outlier", "gap")
                    and i.start
                    and pd.Timestamp(i.start) < window
                ):
                    self.issues_avant.append(i)
                    avant[i.kind] += 1
                else:
                    iss.append(i)
            self.issues += iss
            cnt = Counter(i.kind for i in iss if i.severity != "info")
            premier, dernier = df["date"].min(), df["date"].max()
            semaines = (dernier - premier).days / 7
            lignes.append(
                {
                    "classe": classe, "role": role, "ticker": tk, "statut": "ok",
                    "devise_yahoo": m.get("currency"), "devise_config": ccy_attendue,
                    "premiere_date": premier, "derniere_date": dernier, "barres": len(df),
                    "semaines": round(semaines),
                    "eligible_260s_des": premier + pd.Timedelta(weeks=self.uni.min_history_weeks),
                    "trous": cnt.get("gap", 0), "splits_declares": int((df["splits"] > 0).sum()),
                    "split_suspect": cnt.get("split", 0), "aberrantes": cnt.get("outlier", 0),
                    "doublons": cnt.get("duplicate", 0), "figees": cnt.get("stale", 0),
                    "devise_ecart": cnt.get("currency", 0),
                    "distribution": distribution,
                    "dist_ecart": cnt.get("distribution", 0),
                    "avant_fenetre": sum(avant.values()),
                }
            )  # fmt: skip
        return lignes

    def prices(self) -> None:
        cand = {
            c.ticker: (c.asset_class, c.role, c.currency, c.distribution)
            for c in self.uni.candidates()
        }
        rows = self._price_rows(cand)
        self.data["prices_etf"] = rows
        ok = [r for r in rows if r["statut"] == "ok"]
        s = "## 1. Prix des ETF candidats et de leurs proxys (yfinance)\n\n"
        s += md_table(
            rows,
            ["classe", "role", "ticker", "statut", "devise_yahoo", "devise_config", "premiere_date",
             "derniere_date", "barres", "semaines", "eligible_260s_des", "distribution", "trous",
             "splits_declares", "split_suspect", "aberrantes", "doublons", "figees", "avant_fenetre"],
        )  # fmt: skip
        s += (
            f"\nTickers cités dans l'univers : {len(rows)} ; avec données : {len(ok)} ; "
            f"indisponibles : {len(rows) - len(ok)}. « eligible_260s_des » = première barre + "
            f"{self.uni.min_history_weeks} semaines (L1 §9.1) : c'est une date calendaire, PAS un "
            "décompte de semaines réellement cotées. Les colonnes trous/aberrantes/figees ne comptent "
            f"que les signalements depuis {self.q['window_start']} ; `avant_fenetre` cumule ceux "
            "d'avant ; les « figées » structurelles (liste en config) sont rangées à part en §7. "
            "`distribution` : acc/dist/a_verifier (config) ; `dist_ecart` : incohérence avec les "
            "dividendes enregistrés.\n"
        )
        self.sections.append(s)
        self.backtest_start()
        self.liquidity()
        self.cross_checks()
        self.composition()
        self.drawdowns()

    def backtest_start(self) -> None:
        """Date de début du backtest permise par classe (260 semaines d'historique avant t)."""
        par = {r["ticker"]: r for r in self.data["prices_etf"] if r["statut"] == "ok"}
        w = pd.Timedelta(weeks=self.uni.min_history_weeks)
        lignes = []
        for nom, spec in self.uni.classes.items():
            prim = par.get(spec.primary.ticker)
            d_etf = prim["premiere_date"] + w if prim else None
            d_proxy = None
            if spec.proxy and spec.proxy.ticker in par:
                d_proxy = par[spec.proxy.ticker]["premiere_date"] + w
            premiers = [
                f for f in (self._series_first(s) for s in spec.eur_series) if f is not None
            ]
            d_eur = (min(premiers) + w) if premiers else None
            candidats = [d for d in (d_etf, d_proxy) if d is not None]
            if (
                spec.eur_series_total_return
                and d_eur is not None
                and prim
                and min(premiers) < prim["premiere_date"]
            ):
                candidats.append(
                    d_eur
                )  # série EUR utilisable telle quelle (ex. monétaire capitalisé)
            lignes.append(
                {
                    "classe": nom,
                    "ETF_primaire_seul": d_etf,
                    "avec_proxy_USD_converti": d_proxy if spec.proxy else "interdit (D-011)",
                    "serie_EUR_publique": (
                        (
                            d_eur
                            if prim and min(premiers) < prim["premiere_date"]
                            else f"aucune avant l'ETF (série depuis {min(premiers).date()})"
                        )
                        if spec.eur_series_total_return and premiers
                        else (
                            "taux seulement : reconstruction requise"
                            if spec.eur_series
                            else "aucune"
                        )
                    ),
                    "debut_au_plus_tot": min(candidats) if candidats else None,
                }
            )
        self.data["backtest_start"] = lignes
        s = "### Date de début du backtest permise par les données (260 semaines avant t)\n\n"
        s += md_table(lignes)
        s += (
            "\nLe début global est limité par la classe la plus tardive (colonne `debut_au_plus_tot`). "
            "`serie_EUR_publique` : première date de la série EUR la plus ancienne + 260 semaines.\n"
        )
        valides = [r for r in lignes if r["debut_au_plus_tot"] is not None]
        if len(valides) == len(lignes):
            classees = sorted(valides, key=lambda r: r["debut_au_plus_tot"], reverse=True)
            seuls = [r["ETF_primaire_seul"] for r in lignes if r["ETF_primaire_seul"] is not None]
            self.data["backtest_global"] = {
                "limitante": classees[0]["classe"],
                "debut": str(classees[0]["debut_au_plus_tot"].date()),
                "sans_la_limitante": str(classees[1]["debut_au_plus_tot"].date()),
                "ETF_primaires_seuls": str(max(seuls).date())
                if len(seuls) == len(lignes)
                else None,
            }
            g = self.data["backtest_global"]
            s += (
                f"\n**Début global du backtest : {g['debut']}**, classe limitante "
                f"`{g['limitante']}` ; sans cette classe : {g['sans_la_limitante']} "
                f"(classe suivante : `{classees[1]['classe']}`). Avec les seuls ETF primaires, sans "
                f"proxy : {g['ETF_primaires_seuls']}.\n"
            )
        else:
            s += "\nDate globale non calculable : au moins une classe sans données de prix.\n"
        self.sections.append(s)

    def liquidity(self) -> None:
        since = self.q["liquidity_since"]
        lignes = []
        for c in self.uni.candidates():
            df = self.store.read(f"prices/{c.ticker}")
            st = None if df is None else liquidity_stats(df, since)
            if st is None:
                lignes.append({"ticker": c.ticker, "role": c.role, "statut": "indisponible"})
                continue
            lignes.append({"ticker": c.ticker, "role": c.role, "devise_cotation": c.currency, **st})
        self.data["liquidity"] = lignes
        s = f"### Liquidité depuis {since} (valeur échangée = volume x clôture, devise de cotation)\n\n"
        s += md_table(lignes)
        s += (
            "\nLa valeur médiane par jour mesure le volume de la ligne de cotation lue sur Yahoo, pas "
            "la liquidité réelle de l'ETF (marché primaire, apporteurs de liquidité, autres places) ; "
            "`part_jours_sans_volume` compte les jours à volume nul ou absent.\n"
        )
        self.sections.append(s)

    def cross_checks(self) -> None:
        today = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
        fx = self.store.read("fx/EXR_USD")
        lignes = []
        for nom, spec in self.uni.classes.items():
            if not spec.proxy:
                continue
            p = self.store.read(f"prices/{spec.primary.ticker}")
            x = self.store.read(f"prices/{spec.proxy.ticker}")
            if p is None or x is None or fx is None:
                lignes.append({"classe": nom, "statut": "indisponible"})
                continue
            sp = pit_prices(p, today.date()).set_index("date")["adj_close"]
            sx = pit_prices(x, today.date()).set_index("date")["adj_close"]
            res = cross_check(sp, sx, fx.set_index("date")["rate"])
            ligne = {"classe": nom, "primaire": spec.primary.ticker, "proxy": spec.proxy.ticker}
            ligne.update(res if res else {"statut": "recouvrement insuffisant"})
            lignes.append(ligne)
        self.data["cross_checks"] = lignes
        s = "### Contrôle croisé ETF primaire / proxy converti en EUR (fixing BCE)\n\n"
        s += md_table(lignes)
        s += (
            "\nRatio = primaire (EUR, ajusté dividendes) / proxy (USD ajusté, converti au fixing BCE "
            "du jour, report borné). `derive_annuelle` : moyenne des 60 derniers jours sur celle des "
            "60 premiers, annualisée ; `erreur_suivi_hebdo_annualisee` : écart-type des écarts de "
            "rendements log hebdomadaires (vendredi) x racine de 52. Un ratio stable (faible "
            "coefficient de variation) confirme la devise de cotation du primaire ; l'écart de suivi "
            "inclut la différence d'indice, de réplication, de fiscalité et d'horaire de cotation.\n"
        )
        self.sections.append(s)

    def composition(self) -> None:
        par = {r["ticker"]: r for r in self.data["prices_etf"] if r["statut"] == "ok"}
        prem = {k: v["premiere_date"] for k, v in par.items()}
        dern = {k: v["derniere_date"] for k, v in par.items()}
        eur = {
            sid: self._series_first(sid)
            for spec in self.uni.classes.values()
            for sid in spec.eur_series
        }
        lignes = composition(self.uni, prem, dern, eur)
        self.data["composition"] = lignes
        s = "### Composition de chaque série de classe par date (primaire ou proxy)\n\n"
        s += md_table(lignes, ["classe", "segment", "source", "debut", "fin"])
        proxies = sorted({r["classe"] for r in lignes if "SYNTHÉTIQUE" in str(r.get("source"))})
        s += (
            "\nLe début global du backtest dépend de proxys USD convertis (séries synthétiques avant "
            f"la date de l'ETF) pour : {', '.join(proxies) or 'aucune classe'}. Avant la première date "
            "de l'ETF primaire, ces classes ne reposent donc pas sur le fonds retenu.\n"
        )
        self.sections.append(s)

    def drawdowns(self) -> None:
        cfg = self.cfg["drawdowns"]
        tk = cfg["ticker"]
        px = self.store.read(f"prices/{tk}")
        s = "### Creux (drawdowns) du benchmark proxy, calculés par script\n\n"
        if px is None:
            self.sections.append(s + f"Indisponible : pas de prix pour {tk}.\n")
            self.data["drawdowns"] = []
            return
        taux = self.store.read(f"macro/fred/{cfg['rate_series']}")
        serie_taux = None
        if taux is not None:
            serie_taux = (
                taux.dropna(subset=["value"]).drop_duplicates("date").set_index("date")["value"]
            )
        prix = px.set_index("date")["close"]
        lignes = drawdown_table(prix, cfg["windows"], cfg["threshold"], serie_taux)
        self.data["drawdowns"] = lignes
        dist = next((c.distribution for c in self.uni.candidates() if c.ticker == tk), "a_verifier")
        avert = {
            "acc": "ETF capitalisant : le prix inclut les dividendes réinvestis (équivaut à un rendement total).",
            "dist": "ETF distribuant : prix HORS dividendes versés (le rendement total serait moins négatif).",
        }.get(dist, "Distribution à vérifier : le prix peut exclure les dividendes.")
        s += (
            f"{tk}, clôtures en EUR ({self.uni.reference_currency}), creux d'au moins "
            f"{cfg['threshold']:.0%}, fenêtres {', '.join(cfg['windows'])} jusqu'à la dernière barre. "
            f"{avert} Variation de {cfg['rate_series']} entre le pic et le creux (points de base) ; "
            "un creux dont la fenêtre commence au milieu d'un épisode est tronqué à son plus haut "
            "dans la fenêtre.\n\n"
        )
        cols = ["fenetre", "pic_date", "creux_date", "amplitude", "recuperation",
                "variation_taux_pb", "hausse_des_taux"]  # fmt: skip
        s += md_table(lignes, cols) if lignes else "Aucun creux de ce seuil.\n"
        self.sections.append(s)

    def stocks(self) -> None:
        tick = {t: ("titre", "demo", "USD") for t in self.uni.stock_demo_tickers}
        rows = self._price_rows(tick)
        self.data["prices_stocks"] = rows
        s = "## 2. Prix de la poche titres (liste de démonstration)\n\n"
        s += md_table(
            rows,
            ["ticker", "statut", "premiere_date", "derniere_date", "barres", "trous", "splits_declares",
             "split_suspect", "aberrantes", "doublons", "devise_yahoo"],
        )  # fmt: skip
        self.sections.append(s)

    def _series_first(self, sid: str):
        origine, nom = sid.split(":", 1)
        df = self.store.read(f"macro/{origine}/{nom}")
        if df is None or df.empty:
            return None
        if origine == "fred":
            return df.loc[df["value"].notna(), "date"].min()
        return df["date"].min()

    # ------------------------------------------------------------------ macro et change
    def macro(self) -> None:
        lignes = []
        for sid, spec in self.cfg["fred"]["series"].items():
            df = self.store.read(f"macro/fred/{sid}")
            if df is None:
                lignes.append(
                    {"serie": f"fred:{sid}", "statut": "indisponible", "note": spec["note"]}
                )
                continue
            vals = df[df["value"].notna()]
            self.issues += check_dated_series(vals.drop_duplicates("date"), f"fred:{sid}", 400)
            multi = vals.groupby("date").size()
            lignes.append(
                {
                    "serie": f"fred:{sid}", "statut": "ok", "premiere_obs": vals["date"].min(),
                    "derniere_obs": vals["date"].max(),
                    "observations": int(vals["date"].nunique()),
                    "premier_millesime": df["realtime_start"].min(),
                    "disponibilite": "lag_rule (H)"
                    if "availability" in df and (df["availability"] == "lag_rule").all()
                    else "ALFRED",
                    "lignes_millesimes": len(vals),
                    "obs_revisees": int((multi > 1).sum()),
                    "note": spec["note"],
                }
            )  # fmt: skip
        for nom, spec in self.cfg["ecb"]["series"].items():
            df = self.store.read(f"macro/ecb/{nom}")
            if df is None:
                lignes.append(
                    {"serie": f"ecb:{nom}", "statut": "indisponible", "note": spec["note"]}
                )
                continue
            self.issues += check_dated_series(df, f"ecb:{nom}", 10)
            lignes.append(
                {
                    "serie": f"ecb:{nom}", "statut": "ok", "premiere_obs": df["date"].min(),
                    "derniere_obs": df["date"].max(), "observations": len(df),
                    "disponibilite": "lag_rule (H)",
                    "lignes_millesimes": "aucun millésime", "obs_revisees": "n/d", "note": spec["note"],
                }
            )  # fmt: skip
        self.data["macro"] = lignes
        s = "## 3. Macro (FRED/ALFRED et BCE)\n\n" + md_table(lignes)
        s += (
            "\nLe retard de publication des séries BCE est le délai déclaré en config (H), pas une "
            "mesure. Pour les séries FRED, `premier_millesime` est la date de capture ALFRED la plus ancienne : avant elle, `realtime_start` est un rétro-remplissage, pas un vrai millésime.\n"
        )
        fx_rows = []
        for ccy in self.cfg["ecb"]["fx_currencies"]:
            df = self.store.read(f"fx/EXR_{ccy}")
            if df is None:
                fx_rows.append({"devise": ccy, "statut": "indisponible"})
                continue
            iss = check_dated_series(df, f"fx:{ccy}", self.cfg["ecb"]["fx_max_stale_days"])
            self.issues += iss
            fx_rows.append({"devise": ccy, "statut": "ok", "premier": df["date"].min(),
                            "dernier": df["date"].max(), "fixings": len(df),
                            "trous_sup_seuil": len(iss)})  # fmt: skip
        self.data["fx"] = fx_rows
        s += "\n### Change BCE (EXR)\n\n" + md_table(fx_rows)
        self.sections.append(s)

    # ------------------------------------------------------------------ EDGAR
    def filings(self) -> None:
        cutoff = pd.Timestamp(self.uni.replication_cutoff)
        cutoff_utc = cutoff.tz_localize("UTC")
        comp = self.store.read("filings/_companies")
        sic = {} if comp is None else dict(zip(comp["ticker"], comp["sic"], strict=False))
        lignes = []
        for tk in self.uni.stock_demo_tickers:
            idx = self.store.read(f"filings/index/{tk}")
            if idx is None:
                lignes.append({"ticker": tk, "statut": "indisponible"})
                continue
            self.issues += check_duplicates(idx, ["accession"], f"filings:{tk}")
            texts = idx[
                idx["form"].isin(self.cfg["edgar"]["text_forms"])
                & (idx["filing_date"] >= pd.Timestamp(self.cfg["edgar"]["text_since"]))
            ]
            avec_texte = sum(
                self.store.has_text(f"filings/text/{tk}/{a}") for a in texts["accession"]
            )
            xb = self.store.read(f"xbrl/{tk}")
            lignes.append(
                {
                    "ticker": tk, "statut": "ok", "sic": sic.get(tk),
                    "10-K": int((idx["form"] == "10-K").sum()), "10-Q": int((idx["form"] == "10-Q").sum()),
                    "8-K": int((idx["form"] == "8-K").sum()),
                    "premier_depot_utc": idx["accepted_utc"].min(),
                    "dernier_depot_utc": idx["accepted_utc"].max(),
                    "textes_depuis_text_since": f"{avec_texte}/{len(texts)}",
                    "faits_xbrl": None if xb is None else len(xb),
                    "premier_filed_xbrl": None if xb is None or xb.empty else xb["filed"].min(),
                }
            )  # fmt: skip
        self.data["filings"] = lignes
        s = "## 4. Dépôts SEC EDGAR et XBRL (liste de démonstration)\n\n" + md_table(lignes)
        # pool de réplication
        pool = self.store.read("universe/pool")
        if pool is None:
            s += "\n### Pool de réplication\n\nIndisponible : pool daté non téléchargé.\n"
        else:
            ok_idx = ok_px = ok_both = absents = 0
            manquants: list[str] = []

            def eligible(tk: str) -> tuple[bool, bool, bool]:
                idx = self.store.read(f"filings/index/{tk}")
                px = self.store.read(f"prices/{tk}")
                a = idx is not None and bool(
                    (idx["form"].isin(["10-K", "10-Q"]) & (idx["accepted_utc"] < cutoff_utc)).any()
                )
                b = px is not None and bool(
                    ((px["date"] >= "2024-01-01") & (px["date"] < cutoff)).any()
                )
                return a, b, idx is None or px is None

            for tk in pool["ticker"]:
                a, b, absent = eligible(tk)
                absents += absent
                if absent:
                    manquants.append(tk)
                ok_idx += a
                ok_px += b
                ok_both += a and b
            za, zb, zabs = eligible(self.uni.paper_named_ticker)
            meta = pool.iloc[0]
            self.data["pool"] = {"taille": len(pool), "avec_depot_avant_coupure": ok_idx,
                                 "avec_prix_janvier_2024": ok_px, "utilisables": ok_both,
                                 "donnees_manquantes": absents, "revid": str(meta.get("revid"))}  # fmt: skip
            s += (
                f"\n### Pool de réplication (révision Wikipédia {meta.get('revid')}, "
                f"{meta.get('revision_timestamp')})\n\n"
                f"Titres du secteur dans le pool : {len(pool)} ; avec un 10-K ou 10-Q accepté avant le "
                f"{self.uni.replication_cutoff} : {ok_idx} ; avec des prix en janvier 2024 : {ok_px} ; "
                f"**utilisables (les deux)** : {ok_both} ; titres dont les données n'ont pas pu être "
                f"téléchargées : {absents} ({', '.join(manquants) or 'aucun'} : absents de Yahoo ou "
                f"d'EDGAR, typiquement sociétés rachetées ou radiées, d'où un biais du survivant). "
                f"{self.uni.paper_named_ticker} (titre nommé par le papier) : dans le pool : "
                f"{'oui' if self.uni.paper_named_ticker in set(pool['ticker']) else 'non'} ; "
                f"admissible hors pool (dépôt avant coupure : {'oui' if za else 'non'}, prix de "
                f"janvier 2024 : {'oui' if zb else 'non'}).\n"
            )
        self.sections.append(s)

    # ------------------------------------------------------------------ news
    def news(self) -> None:
        df = self.store.read("news/items")
        s = "## 5. News (RSS, GDELT)\n\n"
        if df is None or df.empty:
            s += "Indisponible : aucun article collecté.\n"
            self.data["news"] = {"total": 0}
            self.sections.append(s)
            return
        self.issues += check_duplicates(df, ["item_id"], "news")
        sources = (
            df.groupby("source")
            .agg(articles=("item_id", "size"), premier=("published_at", "min"),
                 dernier=("published_at", "max"), first_seen_min=("first_seen_at", "min"))
            .reset_index()
        )  # fmt: skip
        s += md_table(sources.to_dict("records"))
        comp = self.store.read("filings/_companies")
        noms = {} if comp is None else dict(zip(comp["ticker"], comp["name"], strict=False))
        semaines = self.store.read("news/_gdelt_weeks")
        lignes = []
        for tk in self.uni.stock_demo_tickers:
            sel = df[df["tags"].str.split("|").apply(lambda x, tk=tk: tk in x)]
            ligne = {"actif": tk, "societe": noms.get(tk), "articles": len(sel),
                     "premier": sel["published_at"].min() if len(sel) else None,
                     "dernier": sel["published_at"].max() if len(sel) else None}  # fmt: skip
            ev = self.store.last_events().get(("gdelt", tk))
            if ev and ev["status"] == "ok":
                ligne["etat_gdelt"] = "sondé (zéro article)" if len(sel) == 0 else "sondé"
            else:
                ligne["etat_gdelt"] = "NON SONDÉ (erreur ou non lancé : pas un zéro article)"
            if semaines is not None and (semaines["tag"] == tk).any():
                sw = semaines[semaines["tag"] == tk]
                seuil = self.q["min_news_weekly_items"]
                ok = int((sw["articles_returned"] >= seuil).sum())
                ligne["semaines_avec_article"] = f"{ok}/{len(sw)}"
                ligne["part_semaines"] = ok / len(sw)
            else:
                ligne["semaines_avec_article"] = "non sondé"
            lignes.append(ligne)
        s += (
            "\n### Couverture par actif (articles GDELT étiquetés au ticker ; semaines sondées une "
            "à une avec `--gdelt-weeks`, présence d'au moins un article)\n\n"
        ) + md_table(lignes)
        mois = df.assign(mois=df["published_at"].dt.strftime("%Y-%m")).groupby("mois").size()
        s += "\n### Couverture par date (articles par mois, toutes sources)\n\n"
        s += md_table([{"mois": m, "articles": int(n)} for m, n in mois.items()])
        probe = self.store.read("news/_gdelt_probe")
        if probe is not None:
            s += "\n### Profondeur historique de GDELT DOC (sondage)\n\n" + md_table(
                probe.to_dict("records")
            )
        else:
            s += "\nSondage de profondeur GDELT : non exécuté.\n"
        s += (
            f"\nFenêtre de collecte : {df['published_at'].min().date()} à {df['published_at'].max().date()}. "
            "Aucun article antérieur au premier jour de collecte n'existe pour les flux RSS ; la "
            "couverture historique des news du backtest dépend donc de la profondeur GDELT mesurée.\n"
        )
        self.data["news"] = {"total": len(df), "par_actif": lignes}
        self.sections.append(s)

    # ------------------------------------------------------------------ ESG
    def esg(self) -> None:
        df = self.store.read("esg/records")
        s = "## 6. ESG\n\n"
        if df is None or df.empty:
            s += "Indisponible : aucun enregistrement ESG.\n"
            self.data["esg"] = {"actifs": 0}
            self.sections.append(s)
            return
        dernier = df.sort_values("observed_at").groupby("asset_id", as_index=False).tail(1)
        n = len(dernier)
        glob = {
            "actifs": n,
            "avec_score": int(dernier["score"].notna().sum()),
            "part_avec_score": float(dernier["score"].notna().mean()),
            # « règle appliquée » : une règle documentée a été appliquée (PAS une détermination)
            "part_avec_determination": float(dernier["determined"].mean()),
            "avec_exclusion_detectee": int((dernier["exclusions"].fillna("") != "").sum()),
        }
        lignes, totaux = esg_matrix(
            df, self.esg_cfg["normative_exclusions"], self.esg_cfg["basis_definitions"]
        )
        self.data["esg"] = {"global": glob, "matrice": lignes, "totaux": totaux}
        s += (
            f"**Score ESG : {glob['avec_score']}/{n} actifs ({glob['part_avec_score']:.0%})** "
            "(l'endpoint gratuit de scores n'a rien renvoyé).\n\n"
            "### Matrice actif x critère (trois états)\n\n"
            f"- `{DETERMINE}` : donnée directe (indicateur fournisseur) ;\n"
            f"- `{SUPPOSE}` : déduit d'une règle (code SIC, méthodologie d'indice déclarée d'après le "
            "nom, non vérifiée) ;\n"
            f"- `{INCONNU}` : aucune information.\n\n"
        )
        s += md_table(lignes)
        crit = {"tobacco": "tabac", "thermal_coal": "charbon thermique",
                "controversial_weapons": "armes controversées"}  # fmt: skip
        s += "\n### Totaux par critère\n\n"
        for c, nom in crit.items():
            tt = totaux[c]
            s += (
                f"- {nom} : {tt[DETERMINE]}/{n} déterminé par donnée, {tt[SUPPOSE]}/{n} supposé par "
                f"règle, {tt[INCONNU]}/{n} inconnu.\n"
            )
        tc = totaux["tous_criteres"]
        s += (
            f"\n**Tous critères ({3 * n} cellules) : {tc[DETERMINE]} déterminé par donnée, "
            f"{tc[SUPPOSE]} supposé par règle, {tc[INCONNU]} inconnu.** Actifs avec au moins une "
            f"exclusion détectée : {glob['avec_exclusion_detectee']}. L'ancien indicateur « exclusion "
            f"déterminée » ({glob['part_avec_determination']:.0%}) signifiait seulement « une règle a "
            "été appliquée » : il n'est plus présenté comme une couverture. « Sans exclusion "
            "détectée » n'est pas une preuve d'absence d'exposition (SIC approximatif ; aucune règle "
            "SIC pour les armes controversées ; contenu des ETF inconnu). Les instantanés ne sont "
            "pas historisés : en strict point-in-time ils ne sont servis qu'après leur date de "
            "collecte.\n"
        )
        self.sections.append(s)

    # ------------------------------------------------------------------ statut et qualité
    def status(self) -> None:
        ev = self.store.last_events()
        agg: dict[str, Counter] = {}
        erreurs = []
        for (source, item), e in ev.items():
            agg.setdefault(source, Counter())[e["status"]] += 1
            if e["status"] != "ok":
                erreurs.append({"source": source, "element": item, "detail": e["detail"][:160]})
        lignes = [{"source": k, **dict(v)} for k, v in sorted(agg.items())]
        s = "## 0. Statut des téléchargements (dernier événement par élément)\n\n"
        s += md_table(lignes) if lignes else "Aucun téléchargement journalisé.\n"
        if erreurs:
            s += "\n### Éléments en erreur ou indisponibles\n\n" + md_table(erreurs)
        self.data["status"] = {"par_source": lignes, "erreurs": erreurs}
        self.sections.insert(0, s)

    def quality(self) -> None:
        w = self.q["window_start"]

        def synth(liste):
            c = Counter((i.kind, i.severity) for i in liste)
            return {k: n for k, n in sorted(c.items())}

        lignes = [
            {"zone": f"depuis {w} (utile)", "type": k, "gravite": sv, "nombre": n}
            for (k, sv), n in synth(self.issues).items()
        ]
        lignes += [
            {"zone": f"avant {w} (hors fenêtre utile)", "type": k, "gravite": sv, "nombre": n}
            for (k, sv), n in synth(self.issues_avant).items()
        ]
        lignes += [
            {"zone": "structurel (liste en config)", "type": k, "gravite": sv, "nombre": n}
            for (k, sv), n in synth(self.issues_struct).items()
        ]
        s = "## 7. Contrôle qualité (signalements, aucune correction appliquée)\n\n"
        s += md_table(lignes) if lignes else "Aucune anomalie détectée sur les séries présentes.\n"
        struct = self.q.get("structural_stale", {})
        if struct:
            s += (
                "\nFaux positifs structurels déclarés (config) : "
                + " ; ".join(f"{k} ({v})" for k, v in struct.items())
                + ".\n"
            )
        graves = [
            i
            for i in self.issues
            if i.severity in ("error", "warning") and i.kind != "short_history"
        ]
        if graves:
            groupes: dict[tuple[str, str], list[QualityIssue]] = {}
            for i in graves:
                groupes.setdefault((i.subject, i.kind), []).append(i)
            lignes_d = []
            for (sujet, kind), liste in groupes.items():
                if kind in ("stale", "outlier") and len(liste) > 3:
                    ex = ", ".join(str(i.start) for i in liste[:3])
                    lignes_d.append({"sujet": sujet, "type": kind, "gravite": "warning",
                                     "occurrences": len(liste), "detail": f"exemples : {ex}"})  # fmt: skip
                else:
                    for i in liste:
                        lignes_d.append({"sujet": sujet, "type": kind, "gravite": i.severity,
                                         "occurrences": 1, "debut": i.start, "detail": i.detail})  # fmt: skip
            s += "\n### Détail (fenêtre utile ; erreurs et avertissements regroupés, hors historique court)\n\n"
            s += md_table(
                lignes_d[:200], ["sujet", "type", "gravite", "occurrences", "debut", "detail"]
            )
        distrib = [i for i in self.issues if i.kind == "distribution" and i.severity == "info"]
        if distrib:
            s += "\n### Distribution à vérifier (config : a_verifier)\n\n" + md_table(
                [{"ticker": i.subject, "detail": i.detail} for i in distrib]
            )
        self.data["quality"] = {
            "synthese": lignes,
            "total": len(self.issues) + len(self.issues_avant) + len(self.issues_struct),
        }
        self.sections.append(s)

    def licences(self) -> None:
        s = (
            "## 8. Licences et limites (texte qualitatif relevé le 2026-10-02, non calculé ; "
            "détail dans la proposition D-0xx)\n\n"
        )
        s += md_table([{"source": k, "licence_et_limites": v} for k, v in LICENCES.items()])
        self.sections.append(s)

    def build(self) -> tuple[str, dict]:
        self.prices()
        self.stocks()
        self.macro()
        self.filings()
        self.news()
        self.esg()
        self.quality()
        self.licences()
        self.status()
        horodatage = datetime.now(UTC).isoformat(timespec="seconds")
        entete = (
            "# Couverture des données (phase 2)\n\n"
            f"Généré le {horodatage} par `python -m amundi_agentic.data.coverage`. "
            "**Ne pas éditer à la main** : chaque chiffre provient du stockage local. "
            "Une source absente est indiquée « indisponible ».\n\n"
        )
        return entete + "\n".join(self.sections), {"generated_at": horodatage, **self.data}


def write_report(settings: DataSettings | None = None, out: Path | None = None) -> Path:
    settings = settings or DataSettings.load()
    texte, data = Report(settings).build()
    par_defaut = out is None
    out = out or ROOT / "docs" / "couverture_donnees.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(texte, encoding="utf-8")
    # JSON : dossier runs/ du dépôt seulement pour la sortie par défaut, sinon à côté de `out`
    js = (
        ROOT / "runs" / "data_coverage" / "couverture.json"
        if par_defaut
        else out.with_suffix(".json")
    )
    js.parent.mkdir(parents=True, exist_ok=True)
    js.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    from amundi_agentic.data.manifest import write_manifest

    write_manifest(settings, js.with_name("data_manifest.json"))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Génère le rapport de couverture des données")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    print(f"rapport écrit : {write_report(out=args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
