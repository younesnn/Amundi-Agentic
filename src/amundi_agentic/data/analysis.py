"""Calculs du rapport de couverture : liquidité, contrôle croisé, matrice ESG, composition."""

from __future__ import annotations

import numpy as np
import pandas as pd

from amundi_agentic.data.universe import Universe, convert_to_eur

DETERMINE, SUPPOSE, INCONNU = "determine_par_donnee", "suppose_par_regle", "inconnu"
CRITERES = ("tobacco", "thermal_coal", "controversial_weapons")


def liquidity_stats(df: pd.DataFrame, since: str = "2018-01-01") -> dict | None:
    """Valeur échangée (volume x clôture, devise de cotation) : médiane, 10e centile, jours sans volume."""
    d = df[df["date"] >= pd.Timestamp(since)]
    if d.empty:
        return None
    valeur = d["volume"] * d["close"]
    return {
        "jours_depuis": len(d),
        "valeur_mediane_par_jour": float(valeur.median()),
        "valeur_p10": float(valeur.quantile(0.10)),
        "part_jours_sans_volume": float((d["volume"].fillna(0) <= 0).mean()),
    }


def cross_check(
    primary: pd.Series, proxy_usd: pd.Series, fx_usd_per_eur: pd.Series, max_stale_days: int = 5
) -> dict | None:
    """Rapport primaire (EUR) / proxy converti en EUR au fixing BCE : niveau, dérive, suivi."""
    proxy_eur, _ = convert_to_eur(proxy_usd, fx_usd_per_eur, max_stale_days)
    d = pd.concat([primary.rename("p"), proxy_eur.rename("x")], axis=1, sort=True).dropna()
    if len(d) < 120:
        return None
    ratio = d["p"] / d["x"]
    ans = (d.index[-1] - d.index[0]).days / 365.25
    derive = (ratio.iloc[-60:].mean() / ratio.iloc[:60].mean()) ** (1 / ans) - 1
    w = d.resample("W-FRI").last().dropna()
    r = np.log(w).diff().dropna()
    return {
        "jours_communs": len(d),
        "debut": d.index[0],
        "fin": d.index[-1],
        "ratio_moyen": float(ratio.mean()),
        "coef_variation": float(ratio.std() / ratio.mean()),
        "derive_annuelle": float(derive),
        "erreur_suivi_hebdo_annualisee": float((r["p"] - r["x"]).std() * np.sqrt(52)),
    }


def esg_matrix(
    records: pd.DataFrame, rules: dict, basis_defs: dict, criteres: tuple[str, ...] = CRITERES
) -> tuple[list[dict], dict]:
    """Matrice actif x critère à trois états : déterminé par donnée, supposé par règle, inconnu.

    - titre : indicateur fournisseur disponible -> déterminé ; sinon règle SIC existante pour le
      critère -> supposé ; sinon inconnu (armes controversées : aucune règle SIC, donc inconnu).
    - ETF : critère listé par la base méthodologique déclarée (indice) -> supposé ; sinon inconnu.
    """
    dernier = records.sort_values("observed_at").groupby("asset_id", as_index=False).tail(1)
    lignes = []
    for r in dernier.itertuples():
        notes = str(getattr(r, "notes", "") or "").split("|")
        ligne = {"actif": r.asset_id, "type": r.kind}
        for c in criteres:
            etat = INCONNU
            if r.kind == "stock":
                if f"vendor_flag:{c}" in notes:
                    etat = DETERMINE
                elif rules.get(c, {}).get("sic_ranges") and getattr(r, "sic", None) not in (
                    None,
                    "",
                ):
                    etat = SUPPOSE if pd.notna(getattr(r, "sic", None)) else INCONNU
            else:
                base = next((n.split(":", 1)[1] for n in notes if n.startswith("basis:")), None)
                defn = basis_defs.get(base or "", {})
                if defn.get("determined", True) and c in defn.get("exclusions", []) and base:
                    etat = SUPPOSE
            ligne[c] = etat
        lignes.append(ligne)
    n = len(lignes)
    totaux = {
        c: {e: sum(1 for ligne in lignes if ligne[c] == e) for e in (DETERMINE, SUPPOSE, INCONNU)}
        for c in criteres
    }
    totaux["tous_criteres"] = {
        e: sum(t[e] for c, t in totaux.items() if c in criteres)
        for e in (DETERMINE, SUPPOSE, INCONNU)
    }
    totaux["actifs"] = n
    return lignes, totaux


def composition(
    uni: Universe,
    premieres: dict[str, pd.Timestamp],
    dernieres: dict[str, pd.Timestamp],
    eur_premieres: dict[str, pd.Timestamp] | None = None,
) -> list[dict]:
    """Composition de chaque série de classe par date : proxy converti (synthétique) puis ETF."""
    lignes = []
    for nom, spec in uni.classes.items():
        p = spec.primary.ticker
        if p not in premieres:
            lignes.append({"classe": nom, "segment": "indisponible", "source": p})
            continue
        d_p = premieres[p]
        if spec.proxy and spec.proxy.ticker in premieres and premieres[spec.proxy.ticker] < d_p:
            lignes.append({"classe": nom, "segment": 1, "source": f"proxy {spec.proxy.ticker} converti en EUR (BCE) : SYNTHÉTIQUE",
                           "debut": premieres[spec.proxy.ticker], "fin": d_p - pd.Timedelta(days=1)})  # fmt: skip
            lignes.append({"classe": nom, "segment": 2, "source": f"ETF primaire {p} (réel)",
                           "debut": d_p, "fin": dernieres[p]})  # fmt: skip
        elif spec.eur_series_total_return and not spec.proxy:
            # une série EUR publique n'est annoncée que si elle existe avant l'ETF
            avant = [
                s for s in spec.eur_series
                if (eur_premieres or {}).get(s) is not None and eur_premieres[s] < d_p
            ]  # fmt: skip
            if avant:
                note = (
                    f"ETF primaire {p} (réel) ; série EUR publique antérieure : {', '.join(avant)}"
                )
            else:
                note = f"ETF primaire {p} seul (réel) ; aucune série EUR publique avant l'ETF"
            lignes.append({"classe": nom, "segment": 1, "source": note, "debut": d_p, "fin": dernieres[p]})  # fmt: skip
        else:
            lignes.append({"classe": nom, "segment": 1, "source": f"ETF primaire {p} seul (réel, aucun proxy admis)" if not spec.proxy else f"ETF primaire {p} (réel)",
                           "debut": d_p, "fin": dernieres[p]})  # fmt: skip
    return lignes


def drawdown_episodes(price: pd.Series, threshold: float = 0.15) -> list[dict]:
    """Creux (pic -> creux -> récupération) d'amplitude >= `threshold`, sur une série de prix.

    Un épisode va d'un plus haut à la date où ce plus haut est de nouveau atteint ; son creux est
    le minimum de l'épisode. Dernier épisode non terminé : récupération None (« non récupéré »).
    """
    s = price.dropna().sort_index()
    if s.empty:
        return []
    sortie: list[dict] = []
    pic_d, pic_p = s.index[0], s.iloc[0]
    creux_d, creux_p = pic_d, pic_p

    def clore(rec):
        ampl = creux_p / pic_p - 1
        if -ampl >= threshold:
            sortie.append(
                {"pic_date": pic_d, "pic_prix": float(pic_p), "creux_date": creux_d,
                 "creux_prix": float(creux_p), "amplitude": float(ampl), "recuperation": rec}
            )  # fmt: skip

    for d, p in s.items():
        if p >= pic_p:
            if creux_p < pic_p:
                clore(d)
            pic_d, pic_p, creux_d, creux_p = d, p, d, p
        elif p < creux_p:
            creux_d, creux_p = d, p
    if creux_p < pic_p:
        clore(None)
    return sortie


def drawdown_table(
    price: pd.Series, windows: list[str], threshold: float, rate: pd.Series | None = None
) -> list[dict]:
    """Creux par fenêtre (début -> fin de la série), avec la variation du taux sur chaque creux."""
    lignes = []
    for debut in windows:
        coupe = price[price.index >= pd.Timestamp(debut)]
        for e in drawdown_episodes(coupe, threshold):
            ligne = {"fenetre": f"{debut} -> {price.index.max().date()}", **e}
            if e["recuperation"] is None:
                ligne["recuperation"] = "non récupéré"
            if rate is not None:
                r = rate.dropna().sort_index()
                y0, y1 = r[r.index <= e["pic_date"]], r[r.index <= e["creux_date"]]
                if len(y0) and len(y1):
                    ligne["dgs10_pic_pct"] = float(y0.iloc[-1])
                    ligne["dgs10_creux_pct"] = float(y1.iloc[-1])
                    ligne["variation_taux_pb"] = float((y1.iloc[-1] - y0.iloc[-1]) * 100)
                    ligne["hausse_des_taux"] = bool(y1.iloc[-1] > y0.iloc[-1])
            lignes.append(ligne)
    return lignes
