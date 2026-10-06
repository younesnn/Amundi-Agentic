"""Débat : collaboration puis round robin, au plus R_max tours (L1 §6, D-009, D-016, EX-O1-07/08).

LangGraph sert uniquement d'ordonnanceur : les noeuds sont nos fonctions, les arêtes conditionnelles
sont décidées par `_routeur` (code Python), tous les appels LLM passent par `LLMClient` (via les
agents). Le consensus est calculé dans `consensus.py` à partir des niveaux structurés ; le LLM ne
déclare jamais « TERMINATE ». Un actif sous veto ESG n'entre jamais dans le débat.

Déroulé :
  collaboration : chaque votant analyse ; l'agent Risque publie ses alertes ; le coordinateur
      consolide un rapport ; les actifs unanimes sont figés ;
  tour r (1..R_max) tant qu'un actif n'est pas unanime : un avocat du diable tournant est désigné
      (son vote compte, aucun appel de plus) ; chaque votant voit les analyses du tour précédent des
      autres et révise ;
  fin : unanime -> n commun ; écart d'un cran -> `consensus` (médiane) ; sinon `contestee`, arbitrée
      par le coordinateur puis bornée à ±1. Confiance : règle de L1 §6.4.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from amundi_agentic.agents.base import LLMAgent
from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import actifs_vetoes, appliquer_veto, filtrer_univers
from amundi_agentic.agents.fundamental import FundamentalAgent
from amundi_agentic.agents.risk import RiskAgent, RiskResult
from amundi_agentic.agents.sentiment import SentimentAgent
from amundi_agentic.agents.valuation import ValuationAgent
from amundi_agentic.debate import consensus as cs
from amundi_agentic.debate import devil as dv
from amundi_agentic.llm.types import ProviderError
from amundi_agentic.schemas import (
    AgentTurn,
    DebateLog,
    DebateOutcome,
    DebateRound,
    Decision5,
    EsgAssessment,
    View,
    VueRejetee,
)

Niveau = Literal["allocation", "titre"]


def construire_votants(ctx: AgentContext, level: Niveau, *, live: bool) -> list[LLMAgent]:
    """Votants dans l'ordre du round robin de `config/debate.yaml`. Sentiment : en live seulement
    (D-044) si `sentiment_vote_en_live_seulement`."""
    cfg = ctx.settings.debate
    fabriques: dict[str, LLMAgent] = {
        "valuation": ValuationAgent(level),
        "sentiment": SentimentAgent(level),
    }
    if level == "allocation":
        from amundi_agentic.agents.macro import MacroAgent

        fabriques["macro"] = MacroAgent()
    else:
        fabriques["fundamental"] = FundamentalAgent()
    votants: list[LLMAgent] = []
    for nom in cfg.ordre_round_robin[level]:
        if nom == "sentiment" and cfg.sentiment_vote_en_live_seulement and not live:
            continue
        votants.append(fabriques[nom])
    return votants


class _Etat(TypedDict, total=False):
    tour: int
    ouverts: list[str]
    tours: list[DebateRound]
    precedent: list[AgentTurn]
    votes: dict[str, dict[str, int]]  # actif -> agent -> n (dernier vote valide)
    vues: dict[str, dict[str, View]]  # actif -> agent -> dernière vue valide
    figes: dict[
        str, tuple[int, int, dict[str, View], list[int], str]
    ]  # actif -> (n, tour, vues, niveaux, statut)
    sans_decision: dict[str, str]
    votants: list[str]
    rapport: str
    trace: list[str]
    sortie: dict[str, Any]


@dataclass
class DebateResult:
    log: DebateLog
    vues_finales: list[View]
    rapport: str
    risque: RiskResult | None
    esg: dict[str, EsgAssessment]
    trace_graphe: list[str] = field(default_factory=list)
    exclus_esg: list[str] = field(default_factory=list)
    arbitrage_repli: list[str] = field(default_factory=list)
    voix_unique_transmise_par_defaut: bool = False  # `debate.transmettre_voix_unique` (YAML)

    def vues_transmises(
        self, neutre_transmis: bool, voix_unique_transmise: bool | None = None
    ) -> list[View]:
        """Vues pour Black-Litterman : une vue NEUTRE est journalisée mais pas transmise (L1 §6.2) ;
        une vue à voix unique (un seul votant valide) non plus, sauf configuration explicite."""
        # la valeur du YAML est le défaut ; l'appelant peut la surcharger explicitement
        voix_unique = (
            self.voix_unique_transmise_par_defaut
            if voix_unique_transmise is None
            else voix_unique_transmise
        )
        return [
            v
            for v in self.vues_finales
            if (neutre_transmis or v.direction != Decision5.NEUTRE)
            and (voix_unique or v.statut != "voix_unique")
        ]


def _debate_id(ctx: AgentContext, level: Niveau, assets: Sequence[str]) -> str:
    cible = "allocation" if level == "allocation" else "-".join(assets)
    return f"{level}-{cible}-{ctx.t.isoformat()}-{ctx.profil}"


def run_debate(
    ctx: AgentContext,
    level: Niveau,
    assets: Sequence[str],
    agents: Sequence[LLMAgent],
    coordinator: Coordinator,
    esg: dict[str, EsgAssessment],
    *,
    risk_agent: RiskAgent | None = None,
) -> DebateResult:
    """Un débat complet. `assets` est filtré par les vetos de `esg` avant tout appel."""
    cfg = ctx.settings
    vetoes = actifs_vetoes(esg)
    exclus = [a for a in assets if a in vetoes]
    autorises = filtrer_univers(assets, vetoes)
    if not autorises:
        raise ValueError("aucun actif autorisé à débattre (tous exclus par l'agent ESG)")
    debut = time.perf_counter()
    usage0 = ctx.llm.usage()

    risque: RiskResult | None = None
    if risk_agent is not None:
        commenter = level == "allocation" or cfg.risk.commenter_titres
        risque = risk_agent.assess(ctx, level, list(autorises), commenter=commenter)
    defaut_alerte = cfg.confidence.alerte_si_indisponible
    n_max = cfg.debate.r_max
    repli: list[str] = []

    def _niveaux_courants(state: _Etat, actif: str) -> list[int]:
        return list(state["votes"][actif].values())

    def _mise_a_jour(state: _Etat, turns: list[AgentTurn], actifs: list[str]) -> None:
        for t in turns:
            for v in t.vues:
                if v.actif in actifs:
                    state["votes"].setdefault(v.actif, {})[t.agent] = v.direction.n
                    state["vues"].setdefault(v.actif, {})[t.agent] = v

    def _geler_unanimes(state: _Etat, tour: int) -> None:
        for a in list(state["ouverts"]):
            niv = _niveaux_courants(state, a)
            if len(niv) < cfg.consensus.min_votants_valides:
                # voix unique : jamais un consensus ; direction bornée à ±1 comme une vue contestée
                n = cs.borner(
                    cs.mediane_vers_zero(niv), min(niv), max(niv), cfg.consensus.borne_contestee
                )
                state["figes"][a] = (n, tour, dict(state["vues"][a]), niv, "voix_unique")
                state["ouverts"].remove(a)
            elif cs.evaluer(niv).unanime:
                state["figes"][a] = (niv[0], tour, dict(state["vues"][a]), niv, "unanime")
                state["ouverts"].remove(a)

    def _tour_record(
        state: _Etat, numero: int, phase: str, devil: str | None, turns: list[AgentTurn]
    ):
        statuts = {
            a: (state["figes"][a][4] if a in state["figes"] else "en_cours")
            for a in [*state["figes"], *state["ouverts"]]
        }
        niveaux = {a: dict(v) for a, v in state["votes"].items()}
        return DebateRound(
            numero=numero,
            phase=phase,  # type: ignore[arg-type]
            avocat_du_diable=devil,
            tours_agents=turns,
            niveaux=niveaux,
            statut_apres_tour=statuts,
        )

    # ------------------------------------------------------------------ noeuds
    def n_collaboration(state: _Etat) -> _Etat:
        turns = [ag.analyse(ctx, autorises, tour=0).turn for ag in agents]
        state["votes"], state["vues"], state["figes"] = {}, {}, {}
        _mise_a_jour(state, turns, list(autorises))
        state["votants"] = [t.agent for t in turns if t.vues]
        sans: dict[str, str] = {}
        for a in autorises:
            if a not in state["votes"]:
                motifs = [
                    r.motif for r in ctx.rejets if a in r.actifs or r.actifs == list(autorises)
                ]
                sans[a] = "aucune vue valide : " + (" | ".join(motifs[:3]) or "agents abstenus")
        state["sans_decision"] = sans
        state["ouverts"] = [a for a in autorises if a in state["votes"]]
        _geler_unanimes(state, 0)
        rapport = (
            coordinator.rapport(ctx, turns, risque, [e for e in esg.values() if e.veto])
            if state["votants"]
            else None
        )
        state["rapport"] = rapport.texte if rapport else "Aucune vue valide : pas de rapport."
        if rapport and rapport.repli:
            repli.append("rapport:" + (rapport.motif_repli or ""))
        state["tour"] = 0
        state["tours"] = [_tour_record(state, 0, "collaboration", None, turns)]
        state["precedent"] = turns
        state["trace"] = ["collaboration"]
        return state

    def n_debat(state: _Etat) -> _Etat:
        tour = state["tour"] + 1
        votants = [n for n in state["votants"]]
        avocat = dv.designer(votants, tour, ctx.t, level, cfg.debate.graine_rotation)
        ouverts = list(state["ouverts"])
        majorite = {a: cs.mediane_vers_zero(_niveaux_courants(state, a)) for a in ouverts}
        precedent = state["precedent"]
        turns: list[AgentTurn] = []
        for ag in agents:
            if ag.name not in votants:
                continue
            try:
                res = ag.revise(
                    ctx, ouverts, precedent, majorite, tour=tour, devil=ag.name == avocat
                )
            except ProviderError as exc:
                # panne du fournisseur pendant une révision (timeout, 503...) : le vote précédent de
                # l'agent est conservé et la panne est journalisée. Un quota épuisé ou une pause
                # (QuotaEpuise, ExecutionPausee) n'est pas capturé : l'exécution s'arrête.
                motif = f"panne du fournisseur ({exc.kind}) : vote précédent conservé"
                ctx.rejets.append(
                    VueRejetee(
                        agent=ag.name, tour=tour, actifs=list(ouverts), motif=motif, tentatives=1
                    )
                )
                turns.append(AgentTurn(agent=ag.name, tour=tour, vues=[]))
                continue
            turns.append(res.turn)
        _mise_a_jour(
            state, turns, ouverts
        )  # vote non révisé (rejet) : le dernier vote valide reste
        state["tour"] = tour
        _geler_unanimes(state, tour)
        state["tours"].append(_tour_record(state, tour, "debat", avocat, turns))
        state["precedent"] = turns
        state["trace"].append(f"debat_{tour}")
        return state

    def _routeur(state: _Etat) -> str:
        return "debat" if state["ouverts"] and state["tour"] < n_max else "fin"

    def n_finaliser(state: _Etat) -> _Etat:
        sorties: dict[str, dict[str, Any]] = {}
        for a, (n, tour, vues, niv, statut_fige) in state["figes"].items():
            sorties[a] = {
                "n": n,
                "statut": statut_fige,
                "tours": tour,
                "vues": vues,
                "niv": niv,
                "arb": None,
            }
        contestes: dict[str, list[View]] = {}
        statuts: dict[str, str] = {}
        for a in state["ouverts"]:
            niv = _niveaux_courants(state, a)
            statuts[a] = cs.statut_apres_rmax(cs.evaluer(niv), cfg.consensus)
            if statuts[a] == "contestee":
                contestes[a] = list(state["vues"][a].values())
        arbitrages = coordinator.arbitrer_lot(ctx, contestes, tour=state["tour"])  # un seul appel
        for a in state["ouverts"]:
            niv = _niveaux_courants(state, a)
            statut = statuts[a]
            arb_txt = None
            if statut == "consensus":
                n = cs.evaluer(niv).mediane
            else:
                arb = arbitrages[a]
                if arb.repli:
                    repli.append(f"arbitrage:{a}")
                n = cs.borner(arb.niveau_choisi, min(niv), max(niv), cfg.consensus.borne_contestee)
                arb_txt = arb.justification
            sorties[a] = {
                "n": n,
                "statut": statut,
                "tours": state["tour"],
                "vues": dict(state["vues"][a]),
                "niv": niv,
                "arb": arb_txt,
            }
        state["sortie"] = sorties
        state["trace"].append("finaliser")
        return state

    if cfg.debate.orchestrateur == "langgraph":
        from langgraph.graph import END, START, StateGraph  # import tardif

        g = StateGraph(_Etat)
        g.add_node("collaboration", n_collaboration)
        g.add_node("debat", n_debat)
        g.add_node("finaliser", n_finaliser)
        g.add_edge(START, "collaboration")
        g.add_conditional_edges("collaboration", _routeur, {"debat": "debat", "fin": "finaliser"})
        g.add_conditional_edges("debat", _routeur, {"debat": "debat", "fin": "finaliser"})
        g.add_edge("finaliser", END)
        # limite de récursion du cadre : au plus R_max + 2 noeuds visités, marge incluse
        final: _Etat = g.compile().invoke(
            {}, {"recursion_limit": n_max + cfg.limites.marge_recursion}
        )
    else:  # alternative D-009 : la même machine à états en boucle Python, sans cadre
        etat: _Etat = n_collaboration({})
        while _routeur(etat) == "debat":
            etat = n_debat(etat)
        final = n_finaliser(etat)

    # ------------------------------------------------------------------ résultats
    resultats: list[DebateOutcome] = []
    vues_finales: list[View] = []
    for a in autorises:
        s = final["sortie"].get(a)
        if s is None:
            continue
        alerte = risque.alerte(a, defaut_alerte) if risque else defaut_alerte
        accord_a = cs.accord(s["niv"], s["n"])
        c = cs.confiance(accord_a, s["statut"], s["tours"], alerte, cfg.confidence)
        # limites de données (ex. découpage RAG en repli) : plafond le plus bas applicable ; une
        # limite ne relève jamais une confiance déjà plus basse
        plafonds = [
            x
            for _, evid in ctx.cache.values()
            for x in evid.limites
            if x.actif in (None, a) and x.plafond_confiance is not None
        ]
        plafonnee_par = None
        if plafonds:
            pire = min(plafonds, key=lambda x: x.plafond_confiance)
            if pire.plafond_confiance < c:
                c = pire.plafond_confiance
                plafonnee_par = f"{pire.texte} (plafond {pire.plafond_confiance})"
        resultats.append(
            DebateOutcome(
                actif=a,
                niveau_final=s["n"],
                statut=s["statut"],
                accord_A=accord_a,
                tours_utilises=s["tours"],
                alerte_risque=alerte,
                confiance_finale=c,
                arbitrage=s["arb"],
                plafonnee_par=plafonnee_par,
            )
        )
        vues = list(s["vues"].values())
        pour = list(dict.fromkeys(x for v in vues for x in v.arguments_pour))
        contre = list(dict.fromkeys(x for v in vues for x in v.arguments_contre))
        sources = list({src.source_id: src for v in vues for src in v.sources}.values())
        vues_finales.append(
            View(
                view_id=f"{ctx.run_id}:finale:{a}:{ctx.t.isoformat()}",
                actif=a,
                niveau_decision=level,
                date_analyse=ctx.t,
                horizon_mois=cfg.debate.horizon_mois,
                direction=Decision5.from_n(s["n"]),
                rendement_excedentaire_attendu=None,
                confiance=c,
                arguments_pour=pour,
                arguments_contre=contre,
                sources=sources,
                profil_risque=ctx.profil,
                auteur="coordinateur",
                statut=s["statut"],
                run_id=ctx.run_id,
            )
        )
    vues_finales = appliquer_veto(vues_finales, vetoes)

    # dernier tour : statuts finaux (consensus, contestee) pour les actifs non figés
    tours = final["tours"]
    statuts_finaux = {o.actif: o.statut for o in resultats}
    tours[-1] = tours[-1].model_copy(
        update={"statut_apres_tour": {**tours[-1].statut_apres_tour, **statuts_finaux}}
    )
    appels, rejets = ctx.vider_journaux()
    usage1 = ctx.llm.usage()
    hashes: dict[str, str] = {}
    for ap in appels:
        hashes[ap.prompt_id] = ap.prompt_sha256
    log = DebateLog(
        debate_id=_debate_id(ctx, level, autorises),
        run_id=ctx.run_id,
        date_analyse=ctx.t,
        niveau_decision=level,
        actifs=[o.actif for o in resultats],
        profil_risque=ctx.profil,
        config=cfg.debate_config(),
        tours=tours,
        rapport_coordinateur=final["rapport"],
        resultats=resultats,
        duree_s=time.perf_counter() - debut,
        tokens_entree=int(usage1["tokens_entree"] - usage0["tokens_entree"]),
        tokens_sortie=int(usage1["tokens_sortie"] - usage0["tokens_sortie"]),
        cout_eur=float(usage1["cout_eur"] - usage0["cout_eur"]),
        votants=final["votants"],
        appels=appels,
        rejets=rejets,
        sans_decision=final["sans_decision"],
        prompt_sha256=hashes,
        risque=risque.assessment if risque else None,
        esg=[e for a, e in esg.items() if a in assets],
    )
    return DebateResult(
        log,
        vues_finales,
        final["rapport"],
        risque,
        esg,
        final["trace"],
        exclus,
        repli,
        cfg.debate.transmettre_voix_unique,
    )
