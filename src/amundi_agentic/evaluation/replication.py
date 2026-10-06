# ruff: noqa: E501, N806, N818
"""Production des décisions de la réplication AlphaAgents (D-065) : un débat par titre, profil et exécution.

Ce module ne calcule AUCUNE performance et n'importe ni `perf` ni `analyse` : la séparation entre la
production des décisions (données strictement antérieures à t) et la mesure après coup est
structurelle (testée). Il ne nomme aucun fournisseur ni modèle : le `LLMClient` vient d'une fabrique.

Reprise : l'état (`etat.json`, écriture atomique) conserve l'enregistrement compact de chaque débat
terminé ; le cache disque du `LLMClient` conserve les appels d'un débat interrompu. Un débat n'est
jamais refait s'il figure dans l'état.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.prompts import ROOT as RACINE_PROMPTS
from amundi_agentic.agents.prompts import PromptLibrary
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.agents.settings import DebateSettings
from amundi_agentic.data.models import LookAheadError
from amundi_agentic.debate.orchestrator import construire_votants, run_debate
from amundi_agentic.evaluation.repl_config import ReplicationConfig
from amundi_agentic.evaluation.sources import EtatPool, SourceReplication
from amundi_agentic.evaluation.tirage import Tirage, tirage_primaire
from amundi_agentic.llm.types import (
    ExecutionPausee,
    ModeleServiChange,
    ProviderError,
    QuotaEpuise,
)
from amundi_agentic.tools.base import ToolError
from amundi_agentic.tools.finance import annualized_volatility

SCHEMA_ETAT = "amundi-agentic/replication-etat/v1"
SAUVER_TOUS_LES = 10

# Classes de rejet (journal de qualité). Les motifs viennent de `agents/base.py` et de l'orchestrateur ;
# tout motif non reconnu est classé « abstention » (un agent n'a rien produit).
PREFIXES_JSON = ("sortie non conforme",)
PREFIXES_ANCRAGE = (
    "chiffres introuvables",
    "source_id inexistant",
    "exactement une vue",
    "vue absente",
    "objection :",
)
PREFIXES_PANNE = ("panne du fournisseur",)


def classer_rejet(motif: str) -> str:
    m = motif.strip().lower()
    if m.startswith(PREFIXES_JSON):
        return "json"
    if m.startswith(PREFIXES_ANCRAGE):
        return "ancrage"
    if m.startswith(PREFIXES_PANNE):
        return "panne"
    return "abstention"


class ReplicationInterrompue(RuntimeError):
    """Arrêt propre (quota, pause, plafond de débats, modèle servi changé) : relancer reprend."""

    def __init__(self, message: str, code: int = 3) -> None:
        super().__init__(message)
        self.code = code


class FabriqueLLM(Protocol):
    def __call__(self, execution: Any, *, cache_dir: Path | None) -> Any: ...


# ------------------------------------------------------------------------------- prompts paraphrasés
class BibliothequeParaphrasee(PromptLibrary):
    """`PromptLibrary` qui lit certains prompts dans un dossier de paraphrases (mêmes noms, en-têtes
    et variables), le reste dans `agent_prompts/`. Chaque fichier garde son propre SHA-256."""

    def __init__(self, dossier_paraphrase: Path, noms: Sequence[str]) -> None:
        super().__init__()
        self._sur = PromptLibrary(dossier_paraphrase)
        self._noms = set(noms)

    def load(self, nom: str):
        return self._sur.load(nom) if nom in self._noms else super().load(nom)


def bibliotheque(
    cfg: ReplicationConfig, paraphrase: str | None, racine: Path | None = None
) -> PromptLibrary:
    if paraphrase is None:
        return PromptLibrary()
    dossier = Path(racine or RACINE_PROMPTS) / cfg.paraphrases.dossier / paraphrase
    return BibliothequeParaphrasee(dossier, cfg.paraphrases.prompts_paraphrases)


# ------------------------------------------------------------------------------- plan et coût
@dataclass
class Plan:
    n_pool: int
    n_utilisables: int
    exclus: dict[str, str]
    titres_evalues: list[str]
    executions: list[str]
    profils: list[str]
    n_debats: int
    appels_par_debat_min: int
    appels_par_debat_max: int
    appels_min: int
    appels_max: int
    appels_secondaires: int
    embeddings: dict[str, Any]
    secondes_par_appel: float | None
    duree_min_h: float | None
    duree_max_h: float | None
    n_tirages_secondaires: int
    graine_sha256: str
    depots_texte: dict[str, int] | None
    avertissements: list[str] = field(default_factory=list)


def appels_par_debat(settings: DebateSettings, n_votants: int) -> tuple[int, int]:
    """Appels LLM d'un débat de titre, hors redemandes d'ancrage et d'erreurs JSON (D-058).
    Minimum : une analyse par votant + le rapport du coordinateur. Maximum : + R_max tours de révision
    de tous les votants + un arbitrage groupé."""
    mini = n_votants + 1
    maxi = n_votants + 1 + n_votants * settings.debate.r_max + 1
    return mini, maxi


def construire_plan(
    cfg: ReplicationConfig,
    etat: EtatPool,
    titres_evalues: Sequence[str],
    executions: Sequence[str],
    settings: DebateSettings,
    *,
    graine_sha: str,
    secondes_par_appel: float | None = None,
    depots_texte: Mapping[str, int] | None = None,
) -> Plan:
    n_votants = len(cfg.evaluation.agents_votants)
    mini, maxi = appels_par_debat(settings, n_votants)
    n_debats = len(titres_evalues) * len(cfg.profils) * len(executions)
    spa = secondes_par_appel if secondes_par_appel is not None else cfg.cout.secondes_par_appel
    avert: list[str] = []
    if depots_texte is not None:
        sans = sorted(t for t in titres_evalues if not depots_texte.get(t))
        if sans:
            avert.append(
                f"{len(sans)} titre(s) évalué(s) sans texte de dépôt dans le stockage : l'agent Fundamental s'abstiendra "
                f"(vote manquant, titre exclu des portefeuilles « signal »). Télécharger les dépôts avant une exécution réelle "
                f"(`amundi-agentic data fetch --sources filings --tickers ...`) ou fixer `pool.depots_texte_requis: true` "
                f"(nouvelle version du pré-enregistrement). Concerné : {', '.join(sans[:8])}{' ...' if len(sans) > 8 else ''}"
            )
    return Plan(
        n_pool=len(etat.pool),
        n_utilisables=len(etat.utilisables),
        exclus=dict(etat.exclus),
        titres_evalues=list(titres_evalues),
        executions=list(executions),
        profils=list(cfg.profils),
        n_debats=n_debats,
        appels_par_debat_min=mini,
        appels_par_debat_max=maxi,
        appels_min=n_debats * mini,
        appels_max=n_debats * maxi,
        appels_secondaires=0,
        embeddings={
            "questions_par_titre": len(settings.fundamental.questions),
            "appels_requete_max_par_titre": len(settings.fundamental.questions),
            "note": (
                "embeddings du RAG (Fundamental) en plus des appels ci-dessus : une requête par question et par titre "
                "(le cache disque les réutilise entre profils et exécutions) et des lots d'indexation des dépôts "
                "(un par `embed_batch` passages, indexés une fois par titre) : nombre de passages inconnu avant indexation"
            ),
        },
        secondes_par_appel=spa,
        duree_min_h=None if spa is None else n_debats * mini * spa / 3600,
        duree_max_h=None if spa is None else n_debats * maxi * spa / 3600,
        n_tirages_secondaires=cfg.tirage.n_tirages_secondaires,
        graine_sha256=graine_sha,
        depots_texte=None if depots_texte is None else dict(depots_texte),
        avertissements=avert,
    )


def rendre_plan(p: Plan) -> str:
    L = [
        "PLAN DE LA RÉPLICATION (aucun appel n'est fait par --plan)",
        f"pool daté : {p.n_pool} titres, {p.n_utilisables} utilisables, {len(p.exclus)} exclus (règle fixée d'avance)",
    ]
    for tk, m in p.exclus.items():
        L.append(f"  exclu {tk} : {m}")
    L += [
        f"titres évalués : {len(p.titres_evalues)} (dont le titre hors pool)",
        f"profils : {', '.join(p.profils)} ; exécutions : {len(p.executions)} ({', '.join(p.executions)})",
        f"débats : {p.n_debats} (un par titre, profil et exécution)",
        f"appels LLM par débat (D-058) : {p.appels_par_debat_min} à {p.appels_par_debat_max}, hors redemandes d'ancrage et erreurs JSON",
        f"appels LLM au total : {p.appels_min} à {p.appels_max}",
        f"tirages secondaires : {p.n_tirages_secondaires}, 0 appel LLM (rééchantillonnage du pool évalué)",
        f"embeddings : {p.embeddings['questions_par_titre']} requêtes par titre au plus (réutilisées par le cache) + lots d'indexation des dépôts (inconnus avant indexation)",
    ]
    if p.duree_min_h is None:
        L.append(
            "durée : non estimée (renseigner --secondes-par-appel ou cout.secondes_par_appel après mesure ; jamais inventée)"
        )
    else:
        L.append(
            f"durée estimée avec {p.secondes_par_appel:g} s par appel (paramètre) : {p.duree_min_h:.1f} à {p.duree_max_h:.1f} h"
        )
    L.append(f"SHA-256 de la graine du tirage : {p.graine_sha256}")
    L += [f"ATTENTION : {a}" for a in p.avertissements]
    return "\n".join(L)


# ------------------------------------------------------------------------------- état
def cle_debat(execution: str, profil: str, ticker: str) -> str:
    return f"{execution}|{profil}|{ticker}"


class Etat:
    """État de reprise (`etat.json`) : écriture atomique, jamais de clé ni de secret."""

    def __init__(self, chemin: Path, cle_config: str) -> None:
        self.chemin = chemin
        self.donnees: dict[str, Any] = {
            "schema": SCHEMA_ETAT,
            "config_sha256": cle_config,
            "debats": {},
            "modeles_servis": {},
            "caracteristiques": {},
            "interrompu": None,
        }
        self._non_sauve = 0
        if chemin.exists():
            lu = json.loads(chemin.read_text(encoding="utf-8"))
            if lu.get("schema") != SCHEMA_ETAT:
                raise ValueError("etat.json : schéma inconnu")
            if lu.get("config_sha256") != cle_config:
                raise ValueError(
                    "reprise refusée : la configuration de la réplication a changé depuis le début de ce dossier"
                )
            self.donnees = lu

    @property
    def debats(self) -> dict[str, Any]:
        return self.donnees["debats"]

    def sauver(self) -> None:
        tmp = self.chemin.with_name(self.chemin.name + f".tmp{os.getpid()}")
        tmp.write_text(
            json.dumps(self.donnees, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        os.replace(tmp, self.chemin)
        self._non_sauve = 0

    def ajouter(self, cle: str, enreg: dict[str, Any]) -> None:
        self.debats[cle] = enreg
        self._non_sauve += 1
        if self._non_sauve >= SAUVER_TOUS_LES:
            self.sauver()

    def observer_modele(self, niveau: str, servi: str) -> None:
        """D-024 : le modèle servi ne doit pas changer au cours de la réplication."""
        connu = self.donnees["modeles_servis"].setdefault(niveau, servi)
        if connu != servi:
            raise ModeleServiChange(
                f"modèle servi modifié pour le niveau {niveau} : {connu} puis {servi} (D-024) : arrêt"
            )


# ------------------------------------------------------------------------------- un débat
def enregistrement_debat(
    res: Any, ticker: str, llm: Any, n_rec0: int, usage0: Mapping[str, float]
) -> dict[str, Any]:
    """Enregistrement compact d'un débat terminé (ce que l'analyse lit ; les prompts sont hashés)."""
    log = res.log
    tour0 = log.tours[0].niveaux.get(ticker, {})
    sortie = next((o for o in log.resultats if o.actif == ticker), None)
    rejets = [
        {
            "agent": r.agent,
            "tour": r.tour,
            "classe": classer_rejet(r.motif),
            "motif": r.motif[:240],
            "tentatives": r.tentatives,
        }
        for r in log.rejets
    ]
    u1 = llm.usage()
    nouveaux = [r for r in llm.records[n_rec0:] if r.erreur is None]
    par_fournisseur: dict[str, int] = {}
    for r in nouveaux:
        if not r.cache_hit:
            par_fournisseur[r.fournisseur] = par_fournisseur.get(r.fournisseur, 0) + 1
    return {
        "statut_debat": "ok",
        "votes_tour0": {a: int(n) for a, n in tour0.items()},
        "final": None
        if sortie is None
        else {
            "niveau": int(sortie.niveau_final),
            "statut": sortie.statut,
            "confiance": float(sortie.confiance_finale),
            "tours": int(sortie.tours_utilises),
            "plafonnee_par": sortie.plafonnee_par,
        },
        "sans_decision": log.sans_decision.get(ticker),
        "votants": list(log.votants),
        "rejets": rejets,
        "prompts_sha256": dict(log.prompt_sha256),
        "modeles_servis": sorted(
            {("embed" if r.tier_demande == "embed" else r.tier, r.modele_servi) for r in nouveaux}
        ),
        "appels_reels": int(u1["appels"] - usage0["appels"]),
        "cache_hits": int(u1["cache_hits"] - usage0["cache_hits"]),
        "par_fournisseur": par_fournisseur,
        "tokens_entree": int(u1["tokens_entree"] - usage0["tokens_entree"]),
        "tokens_sortie": int(u1["tokens_sortie"] - usage0["tokens_sortie"]),
        "duree_s": round(float(log.duree_s), 3),
    }


def _echec(statut: str, motif: str) -> dict[str, Any]:
    return {
        "statut_debat": statut,
        "motif": motif[:240],
        "votes_tour0": {},
        "final": None,
        "sans_decision": None,
        "votants": [],
        "rejets": [],
        "prompts_sha256": {},
        "modeles_servis": [],
        "appels_reels": 0,
        "cache_hits": 0,
        "par_fournisseur": {},
        "tokens_entree": 0,
        "tokens_sortie": 0,
        "duree_s": 0.0,
    }


def un_debat(
    *,
    cfg: ReplicationConfig,
    settings: DebateSettings,
    llm: Any,
    prompts: PromptLibrary,
    profil: str,
    ticker: str,
    fournisseur: Any,
    rag: Any,
    resume: Any,
    run_id: str,
    t: date,
) -> dict[str, Any]:
    """Débat d'un titre pour un profil, sans l'agent Sentiment (D-044), avec les données < t."""
    ctx = AgentContext(
        t=t,
        profil=profil,  # type: ignore[arg-type]
        run_id=run_id,
        llm=llm,
        data=fournisseur,
        settings=settings,
        prompts=prompts,
        rag=rag,
        summarizer=resume,
    )
    usage0, n_rec0 = llm.usage(), len(llm.records)
    esg = EsgAgent().evaluer(ctx, "titre", [ticker])
    if esg[ticker].veto:
        ctx.vider_journaux()
        return _echec("exclu_esg", "veto de l'agent ESG : titre exclu avant tout débat")
    votants = construire_votants(ctx, "titre", live=False)
    if {a.name for a in votants} != set(cfg.evaluation.agents_votants):
        raise ValueError(
            f"votants {[a.name for a in votants]} différents du protocole {cfg.evaluation.agents_votants} (D-044)"
        )
    try:
        res = run_debate(
            ctx, "titre", [ticker], votants, Coordinator(), esg, risk_agent=RiskAgent()
        )
    except (QuotaEpuise, ExecutionPausee, ModeleServiChange):
        raise
    except LookAheadError:
        raise  # une fuite de futur n'est jamais « un échec de données » : arrêt franc
    except (KeyError, ToolError) as exc:
        ctx.vider_journaux()
        return _echec("echec_donnees", f"données indisponibles ({type(exc).__name__}) : {exc}")
    except ProviderError as exc:
        ctx.vider_journaux()
        return _echec("echec_fournisseur", f"{type(exc).__name__} ({exc.kind}) : {exc}")
    return enregistrement_debat(res, ticker, llm, n_rec0, usage0)


def volatilite_avant_t(fournisseur: Any, ticker: str, t: date, fenetre: int) -> float | None:
    """Volatilité annualisée connue à t (outil du quant, séances < t) : sert à la lecture qualitative
    des profils (le portefeuille prudent écarte-t-il les titres volatils ?)."""
    try:
        return float(annualized_volatility(fournisseur.stock_prices(ticker), t, fenetre).value)
    except (KeyError, ToolError, ValueError):
        return None


def echecs_techniques(debats: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """Titres en échec technique, fixés d'avance : une erreur de DONNÉES dans une exécution
    quelconque (déterministe), ou une panne du fournisseur dans l'exécution `baseline` (une panne
    passagère d'une autre exécution n'écarte pas le titre). Jamais une abstention, une décision ou
    une performance."""
    sortie: dict[str, str] = {}
    for cle, d in debats.items():
        ex, _, tk = cle.split("|")
        st = d["statut_debat"]
        if st == "echec_donnees" or (st == "echec_fournisseur" and ex == "baseline"):
            sortie.setdefault(tk, d.get("motif", st))
    return dict(sorted(sortie.items()))


# ------------------------------------------------------------------------------- boucle de décisions
@dataclass
class ResultatDecisions:
    etat: Etat
    tirage: Tirage
    evalues: list[str]
    echecs: dict[str, str]
    interrompu: str | None = None


def produire_decisions(
    cfg: ReplicationConfig,
    source: SourceReplication,
    etat_pool: EtatPool,
    settings: DebateSettings,
    etat: Etat,
    fabrique_llm: FabriqueLLM,
    *,
    executions: Sequence[str],
    univers: str,
    dossier_cache: Path | None,
    max_debats: int | None = None,
    racine: Path | None = None,
    journal: Callable[[str], None] = lambda s: None,
) -> ResultatDecisions:
    """Un débat par (exécution, profil, titre) absent de l'état ; aucune mesure de performance.

    `univers` : `pool` (tous les titres utilisables + le titre hors pool) ou `primaire` (le tirage
    primaire seulement ; un échec technique appelle le titre suivant de la permutation)."""
    t = cfg.cible.date_decision
    hors = cfg.pool.titre_hors_pool
    nouveaux = 0
    interrompu: str | None = None
    echecs_tech: dict[str, str] = {}
    tirage = tirage_primaire(
        etat_pool.utilisables, hors_pool=hors, n=cfg.tirage.n_titres, graine=cfg.tirage.graine
    )

    def cibles() -> list[str]:
        if univers == "pool":
            return sorted({*etat_pool.utilisables, hors})
        return list(tirage.titres)

    deja_evalue: set[str] = set()
    rag = resume = prompts = None
    try:
        while True:
            titres = cibles()
            fournisseur = source.fournisseur_decision(titres, t)
            for ex_nom in executions:
                ex = cfg.execution(ex_nom)
                llm = None
                for profil in cfg.profils:
                    for tk in titres:
                        cle = cle_debat(ex_nom, profil, tk)
                        if cle in etat.debats:
                            continue
                        if max_debats is not None and nouveaux >= max_debats:
                            raise ReplicationInterrompue(
                                f"arrêt volontaire après {nouveaux} débat(s) (--max-debats) : relancer avec --reprendre",
                                code=3,
                            )
                        if llm is None:
                            cache = None if dossier_cache is None else dossier_cache / ex_nom
                            llm = fabrique_llm(ex, cache_dir=cache)
                            rag, resume, avert = source.outils(llm, fournisseur, titres)
                            for a in avert:
                                journal(f"avertissement : {a}")
                            prompts = bibliotheque(cfg, ex.paraphrase, racine)
                        try:
                            enreg = un_debat(
                                cfg=cfg,
                                settings=settings,
                                llm=llm,
                                prompts=prompts,
                                profil=profil,
                                ticker=tk,
                                fournisseur=fournisseur,
                                rag=rag,
                                resume=resume,
                                run_id=f"replication-{ex_nom}",
                                t=t,
                            )
                            for niv, servi in enreg["modeles_servis"]:
                                etat.observer_modele(niv, servi)
                        except (QuotaEpuise, ExecutionPausee) as exc:
                            raise ReplicationInterrompue(
                                f"{type(exc).__name__} : {str(exc)[:200]} : relancer avec --reprendre reprend depuis le cache",
                                code=3,
                            ) from exc
                        except ModeleServiChange as exc:
                            raise ReplicationInterrompue(str(exc)[:300], code=4) from exc
                        etat.ajouter(cle, enreg)
                        nouveaux += 1
                        journal(f"{cle} : {enreg['statut_debat']}")
                for tk in titres:
                    if tk not in etat.donnees["caracteristiques"]:
                        etat.donnees["caracteristiques"][tk] = {
                            "volatilite_annualisee_avant_t": volatilite_avant_t(
                                fournisseur, tk, t, settings.valuation.fenetre_seances
                            )
                        }
            deja_evalue |= set(titres)
            # échecs techniques (données, fournisseur) : titre suivant dans la permutation (univers primaire)
            echecs_tech = echecs_techniques(etat.debats)
            nouveau_tirage = tirage_primaire(
                etat_pool.utilisables,
                hors_pool=hors,
                n=cfg.tirage.n_titres,
                graine=cfg.tirage.graine,
                echecs=echecs_tech,
            )
            if (
                univers == "pool"
                or set(nouveau_tirage.titres) <= deja_evalue
                or nouveau_tirage == tirage
            ):
                tirage = nouveau_tirage
                break
            tirage = nouveau_tirage
    except ReplicationInterrompue as exc:
        interrompu = str(exc)
        etat.donnees["interrompu"] = interrompu
        etat.sauver()
        raise
    etat.donnees["interrompu"] = None
    etat.sauver()
    evalues = sorted(
        {k.split("|")[2] for k, d in etat.debats.items() if k.split("|")[0] in executions}
    )
    return ResultatDecisions(etat, tirage, evalues, echecs_tech, interrompu)


def nombre_attendu(cfg: ReplicationConfig, titres: Sequence[str], executions: Sequence[str]) -> int:
    return len(titres) * len(cfg.profils) * len(executions)


__all__ = [
    "BibliothequeParaphrasee",
    "Etat",
    "Plan",
    "ReplicationInterrompue",
    "appels_par_debat",
    "bibliotheque",
    "classer_rejet",
    "construire_plan",
    "produire_decisions",
    "rendre_plan",
    "un_debat",
]
_ = math
