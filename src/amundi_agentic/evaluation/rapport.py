# ruff: noqa: E501, N806, N818
"""Verdict et rapport de la réplication (D-064, D-065 §10). Les règles sont appliquées par le code.

* « non concluant » si l'intervalle d'une différence contient 0, si moins de `min_titres_differents`
  titres diffèrent entre les portefeuilles comparés, si l'écart est inférieur au désaccord entre
  exécutions (ou si ce désaccord n'est pas mesurable), ou si le multi-agent ne bat pas la règle ET ;
* « multi-agent meilleur » seulement si TOUTES les conditions tiennent sur TOUS les profils ;
* jamais de moyenne entre modèles ; comparaison avec le papier qualitative ; aucun Sharpe sans
  intervalle ; aucune formulation interdite (balayage du texte avant écriture).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

from amundi_agentic.evaluation.repl_config import ReplicationConfig, charger_config

AVERTISSEMENT = "Prototype académique (ESCP, pour Amundi Technology). Ce n'est pas un conseil en investissement."

_TIRETS = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u00ad-"), " ")


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, apostrophes droites, tous les tirets (insécables compris) et blancs
    réduits à une espace : « Multi-Agent  BAT » devient « multi agent bat »."""
    t = unicodedata.normalize("NFKC", texte).replace("\u2019", "'").replace("\u00a0", " ")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t.lower().translate(_TIRETS)).strip()


@lru_cache(maxsize=1)
def _regles() -> tuple[tuple[re.Pattern[str], ...], tuple[str, ...]]:
    """Motifs interdits (config/replication.yaml, `rapport_interdit`) et formules d'étiquette
    autorisées (`modele.*`), normalisés."""
    cfg = charger_config()
    motifs = tuple(re.compile(m) for m in cfg.rapport_interdit.motifs)
    autorisees = tuple(
        normaliser(x) for x in (cfg.modele.etiquette_hors_echantillon, cfg.modele.etiquette_marge)
    )
    return motifs, autorisees


def formulations_interdites(texte: str) -> list[str]:
    """Formulations interdites trouvées (liste vide : texte conforme). « hors échantillon » n'est
    toléré que dans les formules d'étiquette de modèle ; la liste vit dans la configuration."""
    motifs, autorisees = _regles()
    t = normaliser(texte)
    for f in autorisees:
        t = t.replace(f, " ")
    trouvees = [m.pattern for m in motifs if m.search(t)]
    if re.search(r"hors echantillon", t):
        trouvees.append("hors échantillon (hors formule autorisée)")
    return trouvees


class RapportInterdit(ValueError):
    """Le texte généré contient une formulation interdite ou un Sharpe sans intervalle."""


def controler_sharpe_tableaux(md: str) -> list[str]:
    """Toute cellule d'une colonne « Sharpe » d'un tableau doit porter un intervalle `[a ; b]` ou « n/d »."""
    fautes: list[str] = []
    cols: list[int] = []
    for ligne in md.splitlines():
        if not ligne.startswith("|"):
            cols = []
            continue
        cells = [c.strip() for c in ligne.strip().strip("|").split("|")]
        if any("sharpe" in c.lower() for c in cells) and not any(
            re.search(r"\d", c) for c in cells
        ):
            cols = [i for i, c in enumerate(cells) if "sharpe" in c.lower()]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        for i in cols:
            if (
                i < len(cells)
                and cells[i] != "n/d"
                and not re.search(r"\[[^\]]*;[^\]]*\]", cells[i])
            ):
                fautes.append(f"Sharpe sans intervalle : {cells[i]!r}")
    return fautes


# ------------------------------------------------------------------------------- verdict
@dataclass
class Verdict:
    statut: str  # "non_concluant" ou "multi_agent_meilleur"
    raisons: list[str] = field(default_factory=list)
    par_profil: dict[str, dict[str, Any]] = field(default_factory=dict)


def evaluer_comparaison(c: Mapping[str, Any], min_titres: int, exige_gain: bool) -> list[str]:
    """Raisons pour lesquelles une comparaison ne permet pas de conclure (liste vide : conditions réunies)."""
    r: list[str] = []
    nom = f"{c['pour']} contre {c['contre']}"
    if c["delta"] is None or c["bas"] is None:
        return [f"{nom} : différence non calculable"]
    if c["contient_zero"]:
        r.append(f"{nom} : l'intervalle de la différence contient 0")
    if c["titres_differents"] < min_titres:
        r.append(f"{nom} : {c['titres_differents']} titre(s) diffèrent (moins de {min_titres})")
    des = c.get("desaccord_entre_executions")
    if des is None:
        r.append(f"{nom} : désaccord entre exécutions non mesurable (moins de 2 exécutions)")
    elif abs(c["delta"]) < des:
        r.append(f"{nom} : écart inférieur au désaccord entre exécutions")
    if exige_gain and c["delta"] <= 0:
        r.append(f"{nom} : le multi-agent ne fait pas mieux")
    return r


def calculer_verdict(resultats: Mapping[str, Any], cfg: ReplicationConfig) -> Verdict:
    """Verdict sur l'exécution `baseline` (le désaccord vient des autres exécutions)."""
    reg = cfg.regles_rapport
    v = Verdict("multi_agent_meilleur")
    for pf in cfg.profils:
        comps = resultats["executions"]["baseline"][pf]["comparaisons"]
        raisons: list[str] = []
        for c in comps:
            if c["contre"] == "ref15":
                continue  # référence décrite sans inférence de verdict
            if c["contre"] == reg.regle_a_battre or c["contre"] in [
                x for x in reg.comparaisons_agents_seuls
            ]:
                raisons += [
                    f"[{pf}] {x}" for x in evaluer_comparaison(c, reg.min_titres_differents, True)
                ]
        v.par_profil[pf] = {"raisons": raisons, "conditions_reunies": not raisons}
        v.raisons += raisons
    if v.raisons:
        v.statut = "non_concluant"
    return v


def _plus_mois(d: date, n: int) -> date:
    """d + n mois (jour ramené à la fin du mois si besoin)."""
    import calendar

    k = d.month - 1 + n
    y, mo = d.year + k // 12, k % 12 + 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def etiquette_modele(
    servis: Sequence[str],
    cutoffs: Mapping[str, date],
    cfg: ReplicationConfig,
    *,
    simule: bool,
) -> list[tuple[str, str]]:
    """Étiquette de chaque modèle servi, lue dans `training_cutoff` de `config/llm.yaml`."""
    m = cfg.modele
    if simule:
        return [("(simulé)", m.etiquette_simule)]
    sortie = []
    for s in servis:
        cut = cutoffs.get(s) or cutoffs.get(s.split("/", 1)[-1])
        if cut is None:
            sortie.append((s, m.etiquette_inconnue))
        elif cut >= cfg.cible.date_decision:
            sortie.append((s, m.etiquette_contamine))
        elif _plus_mois(cut, m.marge_contamination_mois) >= cfg.cible.date_decision:
            sortie.append((s, m.etiquette_marge))
        else:
            sortie.append((s, m.etiquette_hors_echantillon))
    return sortie


# ------------------------------------------------------------------------------- rendu
def _p(x: float | None, d: int = 2) -> str:
    return "n/d" if x is None else f"{100 * x:.{d}f} %"


def _n(x: float | None, d: int = 2) -> str:
    return "n/d" if x is None else f"{x:.{d}f}"


def fmt_sharpe(valeur: float | None, ic: Sequence[float] | None) -> str:
    """Seule façon d'écrire un Sharpe : toujours avec son intervalle (D-064)."""
    if valeur is None or ic is None:
        return "n/d"
    return f"{valeur:.2f} [{ic[0]:.2f} ; {ic[1]:.2f}]"


NOMS_PF = {
    "valuation_seul": "Valuation seul",
    "fundamental_seul": "Fundamental seul",
    "ET": "ET (sans débat)",
    "OU": "OU (sans débat)",
    "multi_agent": "Multi-agent (débat)",
}


def rendre_rapport(
    cfg: ReplicationConfig,
    res: Mapping[str, Any],
    verdict: Verdict,
    meta: Mapping[str, Any],
) -> str:
    """Rapport Markdown. Chiffres calculés par le code, jamais par un LLM ; vérifié avant retour."""
    L: list[str] = [
        "# Réplication AlphaAgents : rapport (protocole D-065)",
        "",
        f"> {AVERTISSEMENT}",
        "",
    ]
    if meta.get("simule") or meta.get("synthetique"):
        quoi = "LLM simulé" + (" et données synthétiques" if meta.get("synthetique") else "")
        if not meta.get("simule"):
            quoi = "données synthétiques (LLM réel)"
        L += [
            f"> **ESSAI DE MÉCANIQUE : {quoi}.** Kappa = 1 et désaccord entre exécutions = 0 par construction ; "
            "ces résultats n'ont aucune valeur d'évaluation et ne doivent jamais être cités comme résultat de la réplication.",
            "",
        ]
    if verdict.statut == "non_concluant":
        L += ["## Verdict : NON CONCLUANT", ""]
        L += ["Raisons (règles de D-065 §10, appliquées par le code) :", ""] + [
            f"- {r}" for r in verdict.raisons
        ]
    else:
        L += [
            "## Verdict : multi-agent meilleur selon les règles du protocole",
            "",
            "Toutes les conditions de D-065 §10 sont réunies sur les deux profils, pour ce modèle et cette fenêtre unique de quatre mois. "
            "Ce n'est pas une preuve de supériorité : puissance statistique très faible.",
        ]
    L += [
        "",
        "Objet : vérifier la mécanique et la cohérence qualitative avec le papier. Aucune conclusion de performance.",
        "",
    ]
    L += ["## Modèle et étiquette", ""]
    for s, e in meta["etiquettes"]:
        L.append(f"- modèle servi `{s}` : {e}")
    L += ["- les résultats de modèles différents ne sont jamais moyennés.", ""]
    L += ["## Protocole et pré-enregistrement", ""]
    p = meta["preenregistrement"]
    L += [
        f"- date de décision {cfg.cible.date_decision}, suivi jusqu'au {cfg.cible.fin_suivi} inclus ; fenêtre mesurée : {res['fenetre']['entree']} à {res['fenetre']['fin']} ({res['fenetre']['n_seances']} séances) ; prix servis comme `as_of` du {cfg.cible.as_of_performance}",
        f"- pré-enregistrement : {p['statut']}"
        + (f" (SHA-256 {p['sha256']})" if p.get("sha256") else ""),
        f"- SHA-256 de la graine du tirage : {meta['graine_sha256']} ; graine vérifiée contre l'enregistrement : {'oui' if meta['graine_verifiee'] else 'non'}",
        f"- taux sans risque {cfg.taux_sans_risque.serie} : moyenne annuelle {_p(res['fenetre']['rf_annuel'])} ; devise {res['fenetre']['devise']}, prix {res['fenetre']['prix']}",
        "- un seul rééquilibrage (achat et conservation, équipondéré à l'entrée) ; coûts de transaction non modélisés (performance surestimée)",
        "- agent Sentiment exclu (D-044) ; agents votants : "
        + ", ".join(cfg.evaluation.agents_votants),
        "",
    ]
    L += ["## Univers", ""]
    L += [
        f"- pool daté : {meta['n_pool']} titres, {meta['n_utilisables']} utilisables ; titre hors pool : {cfg.pool.titre_hors_pool} (ajouté d'office)",
        "- titres sans données, exclus par la règle fixée d'avance : "
        + (", ".join(f"{k} ({v})" for k, v in meta["exclus"].items()) or "aucun"),
        f"- tirage primaire ({len(res['titres']['primaire'])} titres) : {', '.join(res['titres']['primaire'])}",
        f"- remplacements pour échec technique : {meta['remplaces'] or 'aucun'}",
        f"- titres évalués : {len(res['titres']['evalues'])}",
        "",
    ]
    for ex in meta["executions"]:
        for pf in cfg.profils:
            bloc = res["executions"][ex][pf]
            if ex != "baseline":
                continue
            L += [f"## Décisions et performance : exécution {ex}, profil {pf}", ""]
            L += [
                "| Portefeuille | BUY | SELL | exclus | Rendement cumulé | Volatilité ann. | Sharpe [IC 95 %] | Perte max |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
            for nom in NOMS_PF:
                d, c = bloc["portefeuilles"][nom], bloc["decompte"][nom]["primaire"]
                tr = " (trésorerie)" if d["tresorerie"] else ""
                L.append(
                    f"| {NOMS_PF[nom]}{tr} | {c['BUY']} | {c['SELL']} | {c['exclus']} | {_p(d['cumul'])} | {_p(d['volatilite'])} | {fmt_sharpe(d['sharpe'], d['sharpe_intervalle'])} | {_p(d['perte_max'])} |"
                )
            for nom, lib in (
                ("ref15", "15 titres équipondérés"),
                ("tous_evalues", "tous les titres évalués équipondérés"),
                ("tresorerie", "trésorerie"),
            ):
                d = res["references"][nom]
                L.append(
                    f"| Référence : {lib} | - | - | - | {_p(d['cumul'])} | {_p(d['volatilite'])} | {fmt_sharpe(d['sharpe'], d['sharpe_intervalle'])} | {_p(d['perte_max'])} |"
                )
            L += [
                "",
                "Sensibilité « abstention = BUY » (les titres abstenus sont inclus au portefeuille ; analyse principale : exclus) :",
                "",
                "| Portefeuille | BUY (principal) | BUY (abstention = BUY) | Rendement cumulé (abstention = BUY) |",
                "| --- | --- | --- | --- |",
            ]
            for nom in NOMS_PF:
                ds = bloc["portefeuilles"][nom]["sensibilite_abstention_buy"]
                m0 = bloc["portefeuilles"][nom]["m"]
                L.append(f"| {NOMS_PF[nom]} | {m0} | {ds['m']} | {_p(ds['cumul'])} |")
            ab = res["abstention_par_agent_profil"][ex][pf]
            L += [
                "",
                "Taux d'abstention (aucun vote retenu au tour 0) : "
                + " ; ".join(
                    f"{ag} {_p(v['taux'], 1)} ({v['sans_vote']}/{v['n']})" for ag, v in ab.items()
                )
                + ".",
            ]
            L += [
                "",
                "Portefeuille de même taille tiré au hasard (distribution exacte sur le tirage primaire) :",
                "",
                "| Portefeuille | m | combinaisons | exacte | médiane | centiles 5 / 95 | part des aléatoires au moins aussi bons |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for nom in NOMS_PF:
                a = bloc["portefeuilles"][nom]["aleatoire_meme_taille"]
                if a:
                    L.append(
                        f"| {NOMS_PF[nom]} | {a['m']} | {a['n_combinaisons']} | {'oui' if a['exacte'] else 'échantillon'} | {_p(a['mediane'])} | {_p(a['p05'])} / {_p(a['p95'])} | {_n(a['p_superieur_ou_egal'], 3)} |"
                    )
                else:
                    L.append(f"| {NOMS_PF[nom]} | 0 | - | - | - | - | trésorerie : sans tirage |")
            L.append("")
    arr = res.get("prix_arretes_avant_la_fin", {})
    L += ["## Titres dont les prix s'arrêtent avant la fin du suivi", ""]
    if arr:
        L += [
            "Règle fixée avant les résultats : le portefeuille conserve la dernière clôture connue jusqu'à la fin du suivi (position gelée) ; ces titres ne sont pas exclus.",
            "",
        ] + [
            f"- {tk} : dernière clôture {i.get('derniere_cloture', 'n/d')} ({i.get('seances_gelees', 0)} séance(s) gelée(s))"
            + (
                f" ; première clôture disponible {i['premiere_cloture']}"
                if "premiere_cloture" in i
                else ""
            )
            for tk, i in arr.items()
        ]
    else:
        L.append("Aucun.")
    L += [""]
    L += ["## Différences appariées (bootstrap stationnaire, exécution baseline)", ""]
    L += [
        "| Profil | Comparaison | Différence de rendement cumulé | IC 95 % | Titres différents | Désaccord entre exécutions | Contient 0 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pf in cfg.profils:
        for c in res["executions"]["baseline"][pf]["comparaisons"]:
            L.append(
                f"| {pf} | {c['pour']} contre {c['contre']} | {_p(c['delta'])} | [{_p(c['bas'])} ; {_p(c['haut'])}] | {c['titres_differents']} | {_p(c.get('desaccord_entre_executions'))} | {'oui' if c['contient_zero'] else 'non'} |"
            )
    L += [
        "",
        "Intervalle large publié même s'il est inexploitable (15 titres du même secteur, une fenêtre de quatre mois).",
        "",
    ]
    sec = res["secondaires"]
    L += ["## Tirages secondaires (rééchantillonnage du pool évalué, sans appel LLM)", ""]
    if sec["n_tirages"] == 0:
        L += [sec["note"], ""]
    else:
        L += [
            f"{sec['n_tirages']} tirages de {cfg.tirage.n_titres} titres plus {cfg.pool.titre_hors_pool}. Ils mesurent la variance du choix des titres, pas celle du marché.",
            "",
        ]
        for pf in cfg.profils:
            t = sec["tableau"]["baseline"][pf]
            L += [
                f"Profil {pf}, exécution baseline :",
                "",
                "| Portefeuille | Tirage primaire | Médiane | Centile 5 | Centile 95 |",
                "| --- | --- | --- | --- | --- |",
            ]
            for nom in NOMS_PF:
                L.append(
                    f"| {NOMS_PF[nom]} | {_p(res['executions']['baseline'][pf]['portefeuilles'][nom]['cumul'])} | {_p(t[nom]['mediane'])} | {_p(t[nom]['p05'])} | {_p(t[nom]['p95'])} |"
                )
            et = t["multi_agent_moins_ET"]
            L += [
                "",
                f"Multi-agent moins ET : médiane {_p(et['mediane'])}, centiles 5 / 95 : {_p(et['p05'])} / {_p(et['p95'])} ; part des tirages positifs : {_n(et['part_positive'], 3)}.",
                "",
            ]
    L += ["## Exécutions : accord et plancher de bruit", ""]
    L += [
        "| Profil | Exécution | Titres | Accord avec baseline | IC de Wilson 95 % | Kappa |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for pf in cfg.profils:
        for ex, k in res["kappa"][pf].items():
            w = k["wilson"]
            L.append(
                f"| {pf} | {ex} | {k['n']} | {_n(k['frequence'], 3)} | {'n/d' if w is None else f'[{w[0]:.3f} ; {w[1]:.3f}]'} | {_n(k['kappa'], 3)} |"
            )
    L += [
        "",
        "Accord entre les deux agents au tour 0 (même décision BUY ou SELL) :",
        "",
        "| Exécution | Profil | Titres | Fréquence | IC de Wilson 95 % |",
        "| --- | --- | --- | --- | --- |",
    ]
    for ex in meta["executions"]:
        for pf in cfg.profils:
            a = res["accord"][ex][pf]
            w = a["wilson"]
            L.append(
                f"| {ex} | {pf} | {a['n']} | {_n(a['frequence'], 3)} | {'n/d' if w is None else f'[{w[0]:.3f} ; {w[1]:.3f}]'} |"
            )
    L += [
        "",
        "## Journal de qualité",
        "",
        "| Exécution | Agent | Débats | Rejet d'ancrage | Abstention | Erreur JSON | Panne | Voix unique (débat) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for ex in meta["executions"]:
        q = res["qualite"][ex]
        for ag, a in q["par_agent"].items():
            L.append(
                f"| {ex} | {ag} | {a['n_debats']} | {_p(a['taux_ancrage'], 1)} | {_p(a['taux_abstention'], 1)} | {_p(a['taux_json'], 1)} | {_p(a['taux_panne'], 1)} | {_p(q['taux_voix_unique'], 1)} |"
            )
    L += [
        "",
        "Modèle servi : " + ", ".join(f"{k} = {v}" for k, v in meta["modeles_servis"].items()) + "."
        if meta["modeles_servis"]
        else "Modèle servi : aucun appel enregistré.",
        "",
    ]
    L += ["## Comparaison qualitative avec le papier (aucun chiffre du papier)", ""]
    L += [
        "Titres, modèle, outils et agent Sentiment diffèrent du papier : seule une lecture qualitative est possible.",
        "",
    ]
    L += [
        "| Comportement décrit par le papier | Observé ici (baseline) | Lecture |",
        "| --- | --- | --- |",
    ]
    L += [f"| {a} | {b} | {c} |" for a, b, c in meta["qualitatif"]]
    L += ["", "## Limites", ""]
    L += [
        "- 15 titres d'un même secteur, une seule fenêtre de quatre mois : puissance statistique pratiquement nulle ; aucune conclusion de performance.",
        "- Pool daté de janvier 2024 : biais du survivant ; données de prix actuelles.",
        "- Décisions prises avec des prix en EUR (couche de données), performance mesurée en USD : voir protocole.",
        "- Fundamental : lecture qualitative de dépôts par un LLM ; ET et OU exigent les deux votes ; le multi-agent est mécaniquement plus conservateur à deux votants.",
        "- Contrôle de mémoire (anonymisation, sondage) et réplication jumelle post-coupure : non faits.",
        "- La trajectoire du Sharpe glissant est dans `sharpe_glissant.csv` ; elle n'a pas d'intervalle et n'est pas reprise ici.",
    ]
    texte = "\n".join(L) + "\n"
    interdits = formulations_interdites(texte)
    sh = controler_sharpe_tableaux(texte)
    if interdits or sh:
        raise RapportInterdit(f"formulations interdites : {interdits} ; {sh}")
    return texte
