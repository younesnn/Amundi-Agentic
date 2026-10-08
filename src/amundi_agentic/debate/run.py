"""Une date, un profil : filtre ESG, débat d'allocation, débats par titre, rapport consolidé et
journaux (`runs/<horodatage>/`). Utilisé par la commande `amundi-agentic views` (EX-O1-12).

Un seul débat d'allocation par date, un débat par titre (L1 §6, D-039). lignes'agent ESG filtre avant
tout débat : un actif sous veto n'obtient aucune vue et n'apparaît dans aucune proposition.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent, actifs_vetoes, filtrer_univers
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.debate.orchestrator import DebateResult, construire_votants, run_debate
from amundi_agentic.llm.types import (
    ExecutionPausee,
    PromptTronque,
    ProviderError,
    QuotaEpuise,
    UsageInconnu,
)
from amundi_agentic.schemas import AppelJournal, EsgAssessment, View
from amundi_agentic.tools.base import ToolError

AVERTISSEMENT = "Prototype académique (ESCP, pour Amundi Technology). Ce n'est pas un conseil en investissement."


@dataclass
class RunOutput:
    debats: list[DebateResult] = field(default_factory=list)
    esg: dict[str, EsgAssessment] = field(default_factory=dict)
    appels_esg: list[AppelJournal] = field(default_factory=list)
    vues_finales: list[View] = field(default_factory=list)
    exclus_esg: list[str] = field(default_factory=list)
    ecartes: dict[str, str] = field(default_factory=dict)  # débat écarté sans appel LLM : motif
    rapport_md: str = ""
    # débats qui n'ont pas abouti (panne du fournisseur) : identifiant -> motif ; jamais silencieux
    echecs: dict[str, str] = field(default_factory=dict)
    appels_echecs: list[AppelJournal] = field(default_factory=list)
    interrompu: str | None = (
        None  # quota épuisé ou exécution en pause : arrêt propre, reprise possible
    )


def executer(
    ctx: AgentContext,
    *,
    classes: Sequence[str],
    titres: Sequence[str],
    live: bool = False,
) -> RunOutput:
    """Filtre ESG, débat d'allocation (un), débats de titres (un par titre non exclu)."""
    sortie = RunOutput()
    esg_agent = EsgAgent()
    ev_alloc = esg_agent.evaluer(ctx, "allocation", list(classes)) if classes else {}
    ev_titres = esg_agent.evaluer(ctx, "titre", list(titres)) if titres else {}
    ev_alloc = esg_agent.expliquer(ctx, ev_alloc)
    ev_titres = esg_agent.expliquer(ctx, ev_titres)
    sortie.appels_esg, _ = ctx.vider_journaux()  # appels d'explication, hors débat
    sortie.esg = {**ev_alloc, **ev_titres}
    sortie.exclus_esg = sorted(actifs_vetoes(sortie.esg))
    coord = Coordinator()
    risque = RiskAgent()

    travaux: list[tuple[str, str, list[str], dict[str, EsgAssessment]]] = []
    if classes and not filtrer_univers(classes, actifs_vetoes(ev_alloc)):
        # toutes les classes sont sous veto : débat d'allocation écarté proprement, aucun appel LLM
        sortie.ecartes["allocation"] = (
            "toutes les classes d'actifs demandées sont sous veto de l'agent ESG : "
            "aucun débat d'allocation, aucune vue"
        )
    elif classes:
        travaux.append(("allocation", "allocation", list(classes), ev_alloc))
    for tk in titres:
        if ev_titres[tk].veto:
            continue  # exclu avant tout débat : aucune vue (veto ESG, EX-O1-10)
        travaux.append((f"titre-{tk}", "titre", [tk], {tk: ev_titres[tk]}))
    for nom, niveau, actifs, esg in travaux:
        try:
            sortie.debats.append(
                run_debate(
                    ctx,
                    niveau,  # type: ignore[arg-type]
                    actifs,
                    construire_votants(ctx, niveau, live=live),  # type: ignore[arg-type]
                    coord,
                    esg,
                    risk_agent=risque,
                )
            )
        except (QuotaEpuise, ExecutionPausee) as exc:
            sortie.echecs[nom] = f"{type(exc).__name__} : {exc}"
            sortie.interrompu = sortie.echecs[nom]
            sortie.appels_echecs += ctx.vider_journaux()[0]
            break  # arrêt propre : relancer la même commande reprend depuis le cache
        except (KeyError, ToolError) as exc:  # données absentes du stockage : débat non terminé
            sortie.echecs[nom] = (
                f"données indisponibles ({type(exc).__name__}) : "
                f"{str(exc)[: ctx.settings.limites.motif_max_caracteres]}"
            )
            sortie.appels_echecs += ctx.vider_journaux()[0]
        except (PromptTronque, UsageInconnu) as exc:
            # D-062 : jamais de poursuite sur un prompt tronqué ; le vote précédent n'est
            # conservé que pour les pannes de fournisseur. Les autres débats continuent.
            sortie.echecs[nom] = (
                f"débat non terminé : prompt tronqué (D-062) : {type(exc).__name__} : "
                f"{str(exc)[: ctx.settings.limites.motif_max_caracteres]}"
            )
            sortie.appels_echecs += ctx.vider_journaux()[0]
        except ProviderError as exc:
            sortie.echecs[nom] = (
                f"{type(exc).__name__} ({exc.kind}) : {str(exc)[: ctx.settings.limites.motif_max_caracteres]}"
            )
            sortie.appels_echecs += ctx.vider_journaux()[0]
    sortie.vues_finales = [v for d in sortie.debats for v in d.vues_finales]
    sortie.rapport_md = rendre_rapport(ctx, sortie)
    return sortie


# ----------------------------------------------------------------------------- rapport consolidé
_NIV = {-2: "fortement négatif", -1: "négatif", 0: "neutre", 1: "positif", 2: "fortement positif"}


def rendre_rapport(ctx: AgentContext, sortie: RunOutput) -> str:
    """Rapport consolidé en Markdown. Les chiffres viennent des objets calculés (gabarit), pas du LLM."""
    lignes: list[str] = [
        f"# Rapport consolidé : {ctx.t.isoformat()} (profil {ctx.profil})",
        "",
        f"> {AVERTISSEMENT}",
        "",
    ]
    if sortie.exclus_esg:
        lignes += [
            f"**Actifs exclus par l'agent ESG (veto, aucun débat) :** {', '.join(sortie.exclus_esg)}",
            "",
        ]
    lignes += [
        "## Vues finales",
        "",
        "| Actif | Niveau | Statut | Confiance | Alerte risque | Tours |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in sortie.debats:
        for o in d.log.resultats:
            lignes.append(
                f"| {o.actif} | {_NIV[o.niveau_final]} | {o.statut} | {o.confiance_finale:.2f} | "
                f"{o.alerte_risque} | {o.tours_utilises} |"
            )
    if sortie.ecartes:
        lignes += ["", "**Débats écartés (aucun appel LLM) :**"]
        lignes += [f"- {n} : {m}" for n, m in sortie.ecartes.items()]
    uniques = [o.actif for d in sortie.debats for o in d.log.resultats if o.statut == "voix_unique"]
    if uniques:
        lignes += [
            "",
            "**Vues à voix unique** (un seul agent valide : jamais un consensus ; niveau borné à ±1, "
            "confiance plafonnée, non transmises à la construction du portefeuille par défaut) : "
            + ", ".join(uniques),
        ]
    if sortie.echecs:
        lignes += ["", "**Débats non terminés (panne du fournisseur LLM, aucune vue produite) :**"]
        lignes += [f"- {n} : {m}" for n, m in sortie.echecs.items()]
        if sortie.interrompu:
            lignes += [
                "",
                "Exécution interrompue proprement : relancer la même commande reprend depuis le cache.",
            ]
    plafonnees = [
        (o.actif, o.plafonnee_par)
        for d in sortie.debats
        for o in d.log.resultats
        if o.plafonnee_par
    ]
    if plafonnees:
        lignes += ["", "**Confiance plafonnée par une limite de données :**"]
        lignes += [f"- {a} : confiance plafonnée par : {m}" for a, m in plafonnees]
    sans = {a: m for d in sortie.debats for a, m in d.log.sans_decision.items()}
    if sans:
        lignes += ["", "**Actifs sans vue valide** (rejets du contrôle d'ancrage ou abstentions) :"]
        lignes += [f"- {a} : {m}" for a, m in sans.items()]
    for d in sortie.debats:
        log = d.log
        lignes += [
            "",
            f"## Débat `{log.debate_id}`",
            "",
            f"Votants : {', '.join(log.votants) or 'aucun'} ; "
            f"tours : {len(log.tours) - 1} ; durée {log.duree_s:.1f} s ; "
            f"jetons {log.tokens_entree} entrée / {log.tokens_sortie} sortie ; coût {log.cout_eur:.2f} EUR.",
            "",
            log.rapport_coordinateur,
        ]
        if d.arbitrage_repli:
            lignes += [
                "",
                f"_Replis déterministes (réponse du LLM non retenue) : {', '.join(d.arbitrage_repli)}_",
            ]
        if log.risque is not None:
            lignes += [
                "",
                f"Risque : régime de volatilité {log.risque.regime_volatilite or 'non calculable'} ; "
                f"alertes {json.dumps(log.risque.alertes, ensure_ascii=False)}.",
            ]
            if log.risque.commentaire:
                lignes += ["", log.risque.commentaire]
        for v in [x for x in d.vues_finales]:
            lignes += [
                "",
                f"### {v.actif} : {_NIV[v.direction.n]} ({v.statut}, confiance {v.confiance:.2f})",
                "",
            ]
            lignes += [f"- pour : {a}" for a in v.arguments_pour]
            lignes += [f"- contre : {a}" for a in v.arguments_contre]
            lignes += ["- sources :"]
            lignes += [
                f"  - `{s.source_id}` ({s.type}, {s.date_publication.date().isoformat()}) {s.titre} : {s.extrait}"
                for s in v.sources
            ]
    lignes += [
        "",
        "## ESG et conformité",
        "",
    ]
    if not ctx.settings.esg.etf_criteres_requis:
        lignes += [
            "Aucun critère ETF requis (`esg.etf_criteres_requis` vide) : aucun ETF ne peut être "
            "exclu par l'agent ESG ; les états ci-dessous sont publiés pour information.",
            "",
        ]
    lignes += [
        "| Actif | Veto | " + " | ".join(_criteres(sortie)) + " |",
        "| --- | --- | " + " | ".join("---" for _ in _criteres(sortie)) + " |",
    ]
    for a, e in sortie.esg.items():
        lignes.append(
            f"| {a} | {'oui' if e.veto else 'non'} | "
            + " | ".join(e.etats.get(c, "inconnu") for c in _criteres(sortie))
            + " |"
        )
    lignes += [
        "",
        "Limites : score ESG absent (aucune source gratuite, D-035) ; contrainte CT-06 suspendue ; "
        "« sans exclusion détectée » n'est pas une preuve d'absence d'exposition (H-26).",
    ]
    for a, e in sortie.esg.items():
        if e.veto and not e.point_in_time:
            lignes.append(
                f"- ATTENTION : le veto sur {a} repose sur un enregistrement ESG NON point-in-time "
                "(observé après la date d'analyse ; accepté en mode interactif seulement)."
            )
        if e.veto:
            lignes.append(
                f"- veto sur {a} : {e.explication or '; '.join(m.detail for m in e.motifs)}"
            )
    return "\n".join(lignes) + "\n"


def _criteres(sortie: RunOutput) -> list[str]:
    return sorted({c for e in sortie.esg.values() for c in e.etats})


# ----------------------------------------------------------------------------- écriture des journaux
def ecrire_sorties(dossier: Path, sortie: RunOutput, extra: dict[str, Any]) -> list[Path]:
    """`debates/<debate_id>.json`, `views.json`, `esg.json`, `rapport.md`, `execution.json`.
    (`calls.jsonl` est écrit appel par appel par `LLMClient`.) Les journaux sont écrits une fois :
    aucun fichier existant n'est réécrit (ajout seul)."""
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "debates").mkdir(exist_ok=True)
    ecrits: list[Path] = []

    def ecrire(chemin: Path, texte: str) -> None:
        if chemin.exists():
            raise FileExistsError(f"journal en ajout seul : {chemin} existe déjà")
        chemin.write_text(texte, encoding="utf-8")
        ecrits.append(chemin)

    for d in sortie.debats:
        ecrire(dossier / "debates" / f"{d.log.debate_id}.json", d.log.model_dump_json(indent=1))
    ecrire(
        dossier / "views.json",
        json.dumps(
            [v.model_dump(mode="json") for v in sortie.vues_finales], ensure_ascii=False, indent=1
        ),
    )
    ecrire(
        dossier / "esg.json",
        json.dumps(
            {a: e.model_dump(mode="json") for a, e in sortie.esg.items()},
            ensure_ascii=False,
            indent=1,
        ),
    )
    ecrire(
        dossier / "esg_appels.json",
        json.dumps(
            [a.model_dump(mode="json") for a in sortie.appels_esg], ensure_ascii=False, indent=1
        ),
    )
    if sortie.appels_echecs:
        ecrire(
            dossier / "appels_debats_echoues.json",
            json.dumps(
                [a.model_dump(mode="json") for a in sortie.appels_echecs],
                ensure_ascii=False,
                indent=1,
            ),
        )
    ecrire(dossier / "rapport.md", sortie.rapport_md)
    ecrire(dossier / "execution.json", json.dumps(extra, ensure_ascii=False, indent=1, default=str))
    return ecrits
