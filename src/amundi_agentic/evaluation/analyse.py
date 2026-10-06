# ruff: noqa: E501, N806, N818
"""Mesure après coup et inférence de la réplication (D-065 §6, §9) : seul module qui lit des prix
postérieurs à t. Appelé APRÈS la fin de la production de toutes les décisions (jamais avant) ; il
reçoit l'état des décisions, le tirage et une source de données, et rend un dictionnaire sérialisable.

Aucun appel LLM. Les formules de performance sont celles de `tools/finance.py` (via `perf`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from amundi_agentic.evaluation import inference as inf
from amundi_agentic.evaluation import perf
from amundi_agentic.evaluation.portefeuilles import (
    PORTEFEUILLES,
    Decision,
    decisions,
    etiquette_decision,
)
from amundi_agentic.evaluation.repl_config import ReplicationConfig
from amundi_agentic.evaluation.sources import SourceReplication
from amundi_agentic.evaluation.tirage import Tirage, tirages_secondaires

AGENTS = ("valuation", "fundamental")
CLASSES_REJET = ("ancrage", "abstention", "json", "panne")


def _f(x: Any) -> Any:
    """Valeur JSON sûre : NaN et infinis deviennent None (jamais écrits comme nombres)."""
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, dict):
        return {k: _f(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_f(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def decisions_par_execution(
    debats: Mapping[str, Mapping[str, Any]],
    cfg: ReplicationConfig,
    executions: Sequence[str],
    *,
    abstention_buy: bool,
) -> dict[str, dict[str, dict[str, dict[str, Decision]]]]:
    """exécution -> profil -> titre -> portefeuille -> décision. Seuls les débats terminés (`ok`)
    donnent des décisions ; un titre en échec technique ou exclu par l'ESG est absent (exclu)."""
    sortie: dict[str, dict[str, dict[str, dict[str, Decision]]]] = {
        ex: {p: {} for p in cfg.profils} for ex in executions
    }
    seuil = cfg.mapping.buy_si_niveau_superieur_a
    for cle, enreg in debats.items():
        ex, pf, tk = cle.split("|")
        if ex not in sortie or pf not in sortie[ex] or enreg["statut_debat"] != "ok":
            continue
        sortie[ex][pf][tk] = decisions(enreg, seuil, abstention_buy=abstention_buy)
    return sortie


def _perf_dict(p: perf.Performance, sharpe_ic: tuple[float, float] | None) -> dict[str, Any]:
    d = asdict(p)
    d.pop("sharpe_glissant")
    d["sharpe_intervalle"] = None if sharpe_ic is None else list(sharpe_ic)
    return _f(d)


def analyser(
    cfg: ReplicationConfig,
    source: SourceReplication,
    debats: Mapping[str, Mapping[str, Any]],
    caracteristiques: Mapping[str, Mapping[str, Any]],
    tirage: Tirage,
    evalues: Sequence[str],
    executions: Sequence[str],
) -> dict[str, Any]:
    """Résultats complets de la mesure après coup (voir `resultats.json`)."""
    t, fin = cfg.cible.date_decision, cfg.cible.fin_suivi
    boot = cfg.inference.bootstrap
    ok_titres = sorted(
        {k.split("|")[2] for k, d in debats.items() if d["statut_debat"] == "ok"} & set(evalues)
    )
    primaire = [x for x in tirage.titres]
    titres_mesure = sorted(set(ok_titres) | set(primaire))
    prix = perf.fenetre_suivi(source.prix_suivi(titres_mesure, cfg), t, fin)
    if len(prix) < 3:
        raise ValueError("suivi trop court : moins de 3 séances")
    prix, arrets = perf.geler(prix)  # prix arrêtés : dernière valeur connue, jamais d'exclusion
    taux_pct = source.taux_suivi(cfg)
    taux_ann = perf.taux_quotidiens(taux_pct, prix.index)
    rf = perf.taux_moyen(taux_pct, prix.index[0].date(), fin)
    as_of = cfg.cible.as_of_performance
    glissante = cfg.performance.fenetre_sharpe_glissant
    rel = pd.Series(perf.prix_relatifs(prix, titres_mesure), index=titres_mesure)
    cash_val = perf.valeur_portefeuille(prix, [], taux_ann)
    cash_cum = float(cash_val.iloc[-1] / cash_val.iloc[0] - 1.0)

    def sharpe_ic(r: np.ndarray) -> tuple[float, float] | None:
        return inf.bootstrap_sharpe(
            r,
            rf,
            longueur_moyenne=boot.longueur_moyenne_bloc,
            n_rep=boot.n_reechantillonnages,
            graine=boot.graine,
            niveau=boot.niveau,
        )

    glissants: list[dict[str, Any]] = []

    def evaluer(
        titres: Sequence[str], etiquette: str
    ) -> tuple[dict[str, Any], np.ndarray, pd.Series]:
        v = perf.valeur_portefeuille(prix, list(titres), taux_ann)
        r = perf.rendements(v)
        p = perf.mesurer(v, as_of, fin, rf, glissante)
        if p.sharpe_glissant:
            for d, x in p.sharpe_glissant.items():
                glissants.append({"portefeuille": etiquette, "date": d, "sharpe_glissant": x})
        d = _perf_dict(p, sharpe_ic(r) if p.sharpe is not None else None)
        d["titres"] = list(titres)
        d["m"] = len(titres)
        d["tresorerie"] = len(titres) == 0
        return d, r, v

    references: dict[str, Any] = {}
    ret_ref: dict[str, np.ndarray] = {}
    for nom, tt in (("ref15", primaire), ("tous_evalues", ok_titres)):
        d, r, _ = evaluer(tt, f"reference:{nom}")
        references[nom] = d
        ret_ref[nom] = r
    d_cash, _, _ = evaluer([], "reference:tresorerie")
    references["tresorerie"] = d_cash

    dec = decisions_par_execution(debats, cfg, executions, abstention_buy=False)
    dec_s = decisions_par_execution(debats, cfg, executions, abstention_buy=True)

    def buy(
        par_titre: Mapping[str, Mapping[str, Decision]], pf: str, univers: Sequence[str]
    ) -> list[str]:
        return [x for x in univers if par_titre.get(x, {}).get(pf) == "BUY"]

    resultats_exec: dict[str, Any] = {}
    retours: dict[tuple[str, str, str], np.ndarray] = {}
    holdings: dict[tuple[str, str, str], list[str]] = {}
    for ex in executions:
        resultats_exec[ex] = {}
        for pf in cfg.profils:
            bloc: dict[str, Any] = {"portefeuilles": {}, "comparaisons": [], "decompte": {}}
            for nom in PORTEFEUILLES:
                b = buy(dec[ex][pf], nom, primaire)
                bs = buy(dec_s[ex][pf], nom, primaire)
                d, r, _ = evaluer(b, f"{ex}|{pf}|{nom}")
                ds, rs, _ = evaluer(bs, f"{ex}|{pf}|{nom}|abstention_buy")
                retours[(ex, pf, nom)] = r
                retours[(ex, pf, nom + "|sens")] = rs
                holdings[(ex, pf, nom)] = b
                holdings[(ex, pf, nom + "|sens")] = bs
                n_buy_pool = len(buy(dec[ex][pf], nom, ok_titres))
                n_sell_pool = sum(dec[ex][pf].get(x, {}).get(nom) == "SELL" for x in ok_titres)
                n_buy_p = len(b)
                n_sell_p = sum(dec[ex][pf].get(x, {}).get(nom) == "SELL" for x in primaire)
                bloc["decompte"][nom] = {
                    "primaire": {
                        "BUY": n_buy_p,
                        "SELL": n_sell_p,
                        "exclus": len(primaire) - n_buy_p - n_sell_p,
                    },
                    "pool_evalue": {
                        "BUY": n_buy_pool,
                        "SELL": n_sell_pool,
                        "exclus": len(ok_titres) - n_buy_pool - n_sell_pool,
                    },
                }
                alea = None
                if 1 <= len(b) <= len(primaire):
                    dist = inf.distribution_aleatoire(
                        rel[primaire].to_numpy(),
                        len(b),
                        observe=d["cumul"],
                        max_exact=cfg.distribution_aleatoire.max_exact,
                        n_echantillon=cfg.distribution_aleatoire.n_echantillon,
                        graine=cfg.distribution_aleatoire.graine,
                        cle=f"{ex}|{pf}|{nom}",
                    )
                    alea = _f(asdict(dist))
                d["aleatoire_meme_taille"] = alea
                d["sensibilite_abstention_buy"] = ds
                bloc["portefeuilles"][nom] = d
            # comparaisons appariées (multi-agent contre chaque autre lecture et contre la référence)
            for b_nom in ("ET", "OU", "valuation_seul", "fundamental_seul"):
                bloc["comparaisons"].append(
                    _comparer(cfg, retours, holdings, ex, pf, "multi_agent", b_nom, primaire)
                )
            bloc["comparaisons"].append(
                _comparer_ref(
                    cfg,
                    retours[(ex, pf, "multi_agent")],
                    ret_ref["ref15"],
                    holdings[(ex, pf, "multi_agent")],
                    primaire,
                    ex,
                    pf,
                )
            )
            resultats_exec[ex][pf] = bloc

    # désaccord entre exécutions : écart-type, sur les exécutions, de la différence comparée
    desaccords: dict[str, dict[str, float | None]] = {pf: {} for pf in cfg.profils}
    for pf in cfg.profils:
        noms = [c["contre"] for c in resultats_exec[executions[0]][pf]["comparaisons"]]
        for nom in noms:
            deltas = [
                c["delta"]
                for ex in executions
                for c in resultats_exec[ex][pf]["comparaisons"]
                if c["contre"] == nom and c["delta"] is not None
            ]
            desaccords[pf][nom] = float(np.std(deltas, ddof=1)) if len(deltas) >= 2 else None
        for ex in executions:
            for c in resultats_exec[ex][pf]["comparaisons"]:
                c["desaccord_entre_executions"] = desaccords[pf][c["contre"]]

    secondaires = _secondaires(cfg, dec, executions, ok_titres, rel, cash_cum, ret_ref)
    stats = _stats_accord(cfg, dec, debats, executions, ok_titres)
    return _f(
        {
            "fenetre": {
                "entree": str(prix.index[0].date()),
                "fin": str(prix.index[-1].date()),
                "n_seances": len(prix),
                "n_rendements": len(prix) - 1,
                "rf_annuel": rf,
                "as_of_performance": str(as_of),
                "prix": cfg.cible.prix,
                "devise": cfg.cible.devise_performance,
                "cumul_tresorerie": cash_cum,
            },
            "titres": {"primaire": primaire, "evalues": ok_titres},
            "prix_arretes_avant_la_fin": arrets,
            "references": references,
            "executions": resultats_exec,
            "secondaires": secondaires,
            "accord": stats["accord"],
            "kappa": stats["kappa"],
            "qualite": qualite(debats, executions, cfg),
            "abstention_par_agent_profil": abstentions(debats, cfg, executions),
            "caracteristiques": {k: dict(v) for k, v in caracteristiques.items()},
            "sharpe_glissant": glissants,
        }
    )


def _comparer(
    cfg: ReplicationConfig,
    retours: Mapping[tuple[str, str, str], np.ndarray],
    holdings: Mapping[tuple[str, str, str], list[str]],
    ex: str,
    pf: str,
    a: str,
    b: str,
    primaire: Sequence[str],
) -> dict[str, Any]:
    boot = cfg.inference.bootstrap
    iv = inf.bootstrap_difference_cumulee(
        retours[(ex, pf, a)],
        retours[(ex, pf, b)],
        longueur_moyenne=boot.longueur_moyenne_bloc,
        n_rep=boot.n_reechantillonnages,
        graine=boot.graine,
        niveau=boot.niveau,
    )
    ha, hb = set(holdings[(ex, pf, a)]), set(holdings[(ex, pf, b)])
    return {
        "execution": ex,
        "profil": pf,
        "pour": a,
        "contre": b,
        "delta": iv.estimation,
        "bas": iv.bas,
        "haut": iv.haut,
        "contient_zero": iv.contient_zero,
        "titres_differents": len(ha ^ hb),
        "n_reechantillonnages": iv.n_rep,
    }


def _comparer_ref(
    cfg: ReplicationConfig,
    r_multi: np.ndarray,
    r_ref: np.ndarray,
    h_multi: list[str],
    primaire: Sequence[str],
    ex: str,
    pf: str,
) -> dict[str, Any]:
    boot = cfg.inference.bootstrap
    iv = inf.bootstrap_difference_cumulee(
        r_multi,
        r_ref,
        longueur_moyenne=boot.longueur_moyenne_bloc,
        n_rep=boot.n_reechantillonnages,
        graine=boot.graine,
        niveau=boot.niveau,
    )
    return {
        "execution": ex,
        "profil": pf,
        "pour": "multi_agent",
        "contre": "ref15",
        "delta": iv.estimation,
        "bas": iv.bas,
        "haut": iv.haut,
        "contient_zero": iv.contient_zero,
        "titres_differents": len(set(primaire) ^ set(h_multi)),
        "n_reechantillonnages": iv.n_rep,
    }


def _secondaires(
    cfg: ReplicationConfig,
    dec: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Decision]]]],
    executions: Sequence[str],
    ok_titres: Sequence[str],
    rel: pd.Series,
    cash_cum: float,
    ret_ref: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    """Tirages secondaires : sous-ensembles du pool DÉJÀ ÉVALUÉ (aucun appel LLM). Rendement cumulé
    seulement (achat et conservation, équipondéré) ; médiane et centiles 5 et 95 sur les tirages."""
    hors = cfg.pool.titre_hors_pool
    n_sec = cfg.tirage.n_tirages_secondaires
    pool_eval = [x for x in ok_titres if x != hors]
    if n_sec == 0 or len(pool_eval) < cfg.tirage.n_titres:
        return {
            "n_tirages": 0,
            "note": "tirages secondaires non réalisables (pool évalué trop petit ou nombre nul : univers `primaire` ?)",
            "tableau": {},
        }
    tirages = tirages_secondaires(
        pool_eval,
        hors_pool=hors,
        n=cfg.tirage.n_titres,
        graine=cfg.tirage.graine_secondaires,
        nombre=n_sec,
    )
    colonnes = list(ok_titres)
    pos = {x: i for i, x in enumerate(colonnes)}
    masque = np.zeros((n_sec, len(colonnes)), dtype=bool)
    for k, tt in enumerate(tirages):
        for x in tt:
            masque[k, pos[x]] = True
        if hors in pos:
            masque[k, pos[hors]] = True
    relv = rel[colonnes].to_numpy()
    ref_k = (masque * relv).sum(1) / masque.sum(1) - 1.0

    def q(v: np.ndarray) -> dict[str, float]:
        p05, med, p95 = (float(x) for x in np.quantile(v, [0.05, 0.5, 0.95]))
        return {"p05": p05, "mediane": med, "p95": p95}

    tableau: dict[str, Any] = {"ref15": q(ref_k)}
    for ex in executions:
        tableau[ex] = {}
        for pf in cfg.profils:
            cums: dict[str, np.ndarray] = {}
            for nom in PORTEFEUILLES:
                b = np.array([dec[ex][pf].get(x, {}).get(nom) == "BUY" for x in colonnes])
                sel = masque & b
                cnt = sel.sum(1)
                with np.errstate(divide="ignore", invalid="ignore"):
                    cum = np.where(
                        cnt > 0, (sel * relv).sum(1) / np.maximum(cnt, 1) - 1.0, cash_cum
                    )
                cums[nom] = cum
            tableau[ex][pf] = {
                nom: {**q(c), "part_au_dessus_de_ref15": float(np.mean(c > ref_k))}
                for nom, c in cums.items()
            }
            for autre in ("ET", "OU", "valuation_seul", "fundamental_seul"):
                diff = cums["multi_agent"] - cums[autre]
                tableau[ex][pf][f"multi_agent_moins_{autre}"] = {
                    **q(diff),
                    "part_positive": float(np.mean(diff > 0)),
                }
    return {"n_tirages": n_sec, "tableau": tableau, "titres_par_tirage": cfg.tirage.n_titres + 1}


def _stats_accord(
    cfg: ReplicationConfig,
    dec: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Decision]]]],
    debats: Mapping[str, Mapping[str, Any]],
    executions: Sequence[str],
    ok_titres: Sequence[str],
) -> dict[str, Any]:
    niv = cfg.inference.wilson_niveau
    accord: dict[str, Any] = {}
    kappa: dict[str, Any] = {}
    for ex in executions:
        accord[ex] = {}
        for pf in cfg.profils:
            # accord entre les deux agents au tour 0 (même décision BUY/SELL), titres où les deux ont voté
            both = [x for x in ok_titres if dec[ex][pf].get(x, {}).get("ET") is not None]
            k = sum(
                dec[ex][pf][x]["valuation_seul"] == dec[ex][pf][x]["fundamental_seul"] for x in both
            )
            accord[ex][pf] = {
                "n": len(both),
                "accords": k,
                "frequence": None if not both else k / len(both),
                "wilson": inf.wilson(k, len(both), niv),
            }
    base = "baseline"
    for pf in cfg.profils:
        kappa[pf] = {}
        for ex in executions:
            if ex == base:
                continue
            communs = [x for x in ok_titres if x in dec[base][pf] and x in dec[ex][pf]]
            a = [etiquette_decision(dec[base][pf][x]["multi_agent"]) for x in communs]
            b = [etiquette_decision(dec[ex][pf][x]["multi_agent"]) for x in communs]
            acc = sum(x == y for x, y in zip(a, b, strict=True))
            kappa[pf][ex] = {
                "n": len(communs),
                "accords": acc,
                "frequence": None if not communs else acc / len(communs),
                "wilson": inf.wilson(acc, len(communs), niv),
                "kappa": inf.kappa_cohen(a, b),
            }
    return {"accord": accord, "kappa": kappa}


def qualite(
    debats: Mapping[str, Mapping[str, Any]], executions: Sequence[str], cfg: ReplicationConfig
) -> dict[str, Any]:
    """Journal de qualité : taux de rejet d'ancrage, d'abstention, d'erreur JSON, de panne et de
    `voix_unique`, par agent et par exécution (dénominateur : débats terminés de l'exécution)."""
    sortie: dict[str, Any] = {}
    for ex in executions:
        lignes = [d for k, d in debats.items() if k.split("|")[0] == ex]
        ok = [d for d in lignes if d["statut_debat"] == "ok"]
        n = len(ok)
        par_agent: dict[str, Any] = {}
        for ag in AGENTS:
            cpt = dict.fromkeys(CLASSES_REJET, 0)
            sans_vote_t0 = 0
            for d in ok:
                classes_vues = {
                    r["classe"] for r in d["rejets"] if r["agent"] == ag and r["tour"] == 0
                }
                for c in classes_vues:
                    cpt[c] += 1
                if ag not in d["votes_tour0"]:
                    sans_vote_t0 += 1
            par_agent[ag] = {
                "n_debats": n,
                **{f"debats_avec_{c}": cpt[c] for c in CLASSES_REJET},
                **{f"taux_{c}": (cpt[c] / n if n else None) for c in CLASSES_REJET},
                "sans_vote_tour0": sans_vote_t0,
            }
        vu = sum(1 for d in ok if d["final"] is not None and d["final"]["statut"] == "voix_unique")
        sans = sum(1 for d in ok if d["final"] is None)
        sortie[ex] = {
            "n_debats_demandes": len(lignes),
            "n_debats_ok": n,
            "echecs_donnees": sum(d["statut_debat"] == "echec_donnees" for d in lignes),
            "echecs_fournisseur": sum(d["statut_debat"] == "echec_fournisseur" for d in lignes),
            "exclus_esg": sum(d["statut_debat"] == "exclu_esg" for d in lignes),
            "par_agent": par_agent,
            "voix_unique": vu,
            "taux_voix_unique": vu / n if n else None,
            "sans_decision_finale": sans,
            "appels_reels": sum(d["appels_reels"] for d in lignes),
            "cache_hits": sum(d["cache_hits"] for d in lignes),
            "tokens_entree": sum(d["tokens_entree"] for d in lignes),
            "tokens_sortie": sum(d["tokens_sortie"] for d in lignes),
            "prompts_sha256": _fusion_hashes(lignes),
        }
    return sortie


def _fusion_hashes(lignes: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    sortie: dict[str, set[str]] = {}
    for d in lignes:
        for k, v in d["prompts_sha256"].items():
            sortie.setdefault(k, set()).add(v)
    return {k: sorted(v) for k, v in sorted(sortie.items())}


def abstentions(
    debats: Mapping[str, Mapping[str, Any]], cfg: ReplicationConfig, executions: Sequence[str]
) -> dict[str, Any]:
    """Taux d'abstention (aucun vote valide au tour 0) par exécution, profil et agent : publié à
    côté de la sensibilité « abstention = BUY »."""
    sortie: dict[str, Any] = {}
    for ex in executions:
        sortie[ex] = {}
        for pf in cfg.profils:
            ok = [
                d
                for k, d in debats.items()
                if k.split("|")[:2] == [ex, pf] and d["statut_debat"] == "ok"
            ]
            sortie[ex][pf] = {
                ag: {
                    "n": len(ok),
                    "sans_vote": sum(ag not in d["votes_tour0"] for d in ok),
                    "taux": (sum(ag not in d["votes_tour0"] for d in ok) / len(ok)) if ok else None,
                }
                for ag in AGENTS
            }
    return sortie
