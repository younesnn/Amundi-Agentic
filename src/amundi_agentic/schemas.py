"""Modèles Pydantic partagés (D-010, L1 section 5).

Ce module n'importe aucun autre module du paquet (L1 3.2) : `portfolio/` peut ainsi connaître
`View` sans dépendre de `agents/` ni de `llm/`.

Aucune valeur numérique d'hypothèse (H) n'est codée ici : les paramètres du débat, des seuils et
de la confiance vivent dans `config/`. Les contraintes ci-dessous sont des invariants de forme
(bornes de probabilité, ordre des dates, tailles minimales).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

PARIS = ZoneInfo("Europe/Paris")

# Identifiants de l'univers (config/universe.yaml) qui ne peuvent porter aucune vue : le monétaire
# est l'actif résiduel (EX-O2-12).
ACTIFS_SANS_VUE = frozenset({"monetaire_euro"})

_SHA256 = re.compile(r"[0-9a-f]{64}")


class _Modele(BaseModel):
    """Base : champs inconnus refusés (une sortie de LLM ne glisse pas de champ en douce) et
    NaN ou infini refusés."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def coupure(t: date) -> datetime:
    """Coupure point-in-time de la date d'analyse t : t 00:00 Europe/Paris (L1 11.3)."""
    return datetime(t.year, t.month, t.day, tzinfo=PARIS)


# --------------------------------------------------------------------------- décision à 5 niveaux


class Decision5(StrEnum):
    """Décision à 5 niveaux (L1 5.1, EX-O1-09)."""

    FORTEMENT_NEGATIF = "FORTEMENT_NEGATIF"
    NEGATIF = "NEGATIF"
    NEUTRE = "NEUTRE"
    POSITIF = "POSITIF"
    FORTEMENT_POSITIF = "FORTEMENT_POSITIF"

    @property
    def n(self) -> int:
        """Code numérique de −2 à +2 (L1 5.1)."""
        return _NIVEAUX[self]

    @classmethod
    def from_n(cls, n: int) -> Decision5:
        for decision, code in _NIVEAUX.items():
            if code == n:
                return decision
        raise ValueError(f"niveau {n!r} hors de [-2, 2]")


_NIVEAUX = {
    Decision5.FORTEMENT_NEGATIF: -2,
    Decision5.NEGATIF: -1,
    Decision5.NEUTRE: 0,
    Decision5.POSITIF: 1,
    Decision5.FORTEMENT_POSITIF: 2,
}

NiveauDecision = Literal["allocation", "titre"]
ProfilRisque = Literal["prudent", "equilibre", "dynamique", "risk_averse", "risk_neutral"]
StatutVue = Literal["individuelle", "unanime", "consensus", "contestee", "surcharge_gerant"]
NiveauAlerte = Literal["aucune", "moderee", "elevee"]

# --------------------------------------------------------------------------- source et vue


class Source(_Modele):
    """Source citée par une vue (L1 5.2, EX-O1-03)."""

    source_id: str = Field(min_length=1)
    type: Literal["prix", "macro", "depot_sec", "news", "esg", "sortie_outil"]
    titre: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    # Instant où l'information est devenue publique ; pour `sortie_outil` : instant de la dernière
    # donnée utilisée par l'outil. Toujours avec fuseau ; ramené en UTC.
    date_publication: AwareDatetime
    extrait: str = Field(max_length=500)

    @field_validator("date_publication")
    @classmethod
    def _en_utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC)


class View(_Modele):
    """Vue d'un agent ou vue finale (section 3.4 du prompt, L1 5.2)."""

    view_id: str = Field(min_length=1)
    actif: str = Field(min_length=1)
    niveau_decision: NiveauDecision
    date_analyse: date
    horizon_mois: int = Field(default=3, ge=1, le=12)
    direction: Decision5
    # Décimal annualisé (0,02 = 2 %), rempli par portfolio/views.py, jamais par le LLM (EX-O1-05).
    rendement_excedentaire_attendu: float | None = None
    confiance: float = Field(ge=0, le=1)
    arguments_pour: list[str] = Field(min_length=1)
    arguments_contre: list[str] = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    profil_risque: ProfilRisque
    auteur: str = Field(min_length=1)
    statut: StatutVue
    run_id: str = Field(min_length=1)

    @field_validator("date_analyse", mode="before")
    @classmethod
    def _date_sans_heure(cls, v: Any) -> Any:
        # Un datetime n'est pas une date d'analyse : refus plutôt que troncature silencieuse.
        if isinstance(v, datetime):
            raise ValueError("date_analyse doit être une date (AAAA-MM-JJ), pas un instant")
        return v

    @field_validator("rendement_excedentaire_attendu")
    @classmethod
    def _decimal_pas_pourcentage(cls, v: float | None) -> float | None:
        # Garde-fou d'unité : 2 (pour 2 %) serait pris pour 200 %. Un rendement annualisé de plus
        # de 100 % est refusé : règle de format, pas une hypothèse de marché.
        if v is not None and abs(v) > 1:
            raise ValueError("rendement en décimal annualisé (0,02 = 2 %), |valeur| <= 1")
        return v

    @model_validator(mode="after")
    def _regles_metier(self) -> View:
        limite = coupure(self.date_analyse)
        for s in self.sources:
            if s.date_publication >= limite:
                raise ValueError(
                    f"source {s.source_id} publiée le {s.date_publication.isoformat()}, "
                    f"à ou après la coupure {limite.isoformat()} (point-in-time, EX-O1-03)"
                )
        if self.statut == "contestee" and abs(self.direction.n) > 1:
            raise ValueError("une vue contestée est bornée à ±1 (L1 6.2)")
        if self.actif in ACTIFS_SANS_VUE:
            raise ValueError(f"{self.actif} est l'actif résiduel : aucune vue (EX-O2-12)")
        return self


# --------------------------------------------------------------------------- sorties d'agents


class ToolCall(_Modele):
    outil: str = Field(min_length=1)
    parametres: dict[str, Any]
    resultat: Any
    duree_ms: int = Field(ge=0)
    date_derniere_donnee: date | None = None


class AgentTurn(_Modele):
    agent: str = Field(min_length=1)
    tour: int = Field(ge=0)
    role: Literal["normal", "avocat_du_diable"] = "normal"
    vues: list[View] = Field(default_factory=list)
    objection: str | None = None
    revision_motif: str | None = None
    appels_outils: list[ToolCall] = Field(default_factory=list)
    appel_id: str | None = None

    @model_validator(mode="after")
    def _objection_de_l_avocat(self) -> AgentTurn:
        if self.role == "avocat_du_diable" and not (self.objection and self.objection.strip()):
            raise ValueError("l'avocat du diable doit produire une objection (L1 6.3)")
        return self


class RiskAssessment(_Modele):
    """Alertes de l'agent Risque : calculées par seuils Python, le LLM ne fait que commenter."""

    date_analyse: date
    alertes: dict[str, NiveauAlerte]
    regime_volatilite: Literal["normal", "haut"]
    indicateurs: dict[str, float]
    seuils: dict[str, float]
    commentaire: str = ""
    sources: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sources_avant_la_coupure(self) -> RiskAssessment:
        limite = coupure(self.date_analyse)
        for s in self.sources:
            if s.date_publication >= limite:
                raise ValueError(f"source {s.source_id} à ou après la coupure {limite.isoformat()}")
        return self


# --------------------------------------------------------------------------- journal de débat


class DebateConfig(_Modele):
    """Paramètres du débat : valeurs lues dans config/debate.yaml, aucune valeur par défaut."""

    r_max: int = Field(ge=0)
    parametres_confiance: dict[str, float]
    graine_rotation: int


class DebateRound(_Modele):
    numero: int = Field(ge=0)
    phase: Literal["collaboration", "debat", "contestation_gerant"]
    avocat_du_diable: str | None = None
    tours_agents: list[AgentTurn]
    niveaux: dict[str, dict[str, int]]  # actif -> agent -> n
    statut_apres_tour: dict[str, str]

    @model_validator(mode="after")
    def _coherence(self) -> DebateRound:
        if (self.numero == 0) != (self.phase == "collaboration"):
            raise ValueError("le tour 0 est la collaboration, et seulement lui (L1 5.4)")
        for actif, par_agent in self.niveaux.items():
            for agent, n in par_agent.items():
                if not -2 <= n <= 2:
                    raise ValueError(f"niveau {n} de {agent} sur {actif} hors de [-2, 2]")
        return self


class DebateOutcome(_Modele):
    actif: str
    niveau_final: int = Field(ge=-2, le=2)
    statut: Literal["unanime", "consensus", "contestee"]
    accord_A: float = Field(ge=0, le=1)  # noqa: N815 (notation de L1 6.4)
    tours_utilises: int = Field(ge=0)
    alerte_risque: NiveauAlerte
    confiance_finale: float = Field(ge=0, le=1)
    arbitrage: str | None = None

    @model_validator(mode="after")
    def _contestee_bornee(self) -> DebateOutcome:
        if self.statut == "contestee" and abs(self.niveau_final) > 1:
            raise ValueError("niveau final d'une vue contestée borné à ±1 (L1 6.2)")
        return self


class DebateLog(_Modele):
    debate_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    date_analyse: date
    niveau_decision: NiveauDecision
    actifs: list[str]
    profil_risque: str
    config: DebateConfig
    tours: list[DebateRound]
    rapport_coordinateur: str
    resultats: list[DebateOutcome]
    duree_s: float = Field(ge=0)
    tokens_entree: int = Field(ge=0)
    tokens_sortie: int = Field(ge=0)
    cout_eur: float = Field(ge=0)

    @model_validator(mode="after")
    def _un_resultat_par_actif(self) -> DebateLog:
        if sorted(o.actif for o in self.resultats) != sorted(self.actifs):
            raise ValueError("un résultat exactement par actif débattu (L1 5.4)")
        return self


# --------------------------------------------------------------------------- exécution


ModeExecution = Literal["interactif", "evaluation"]
TierEffectif = Literal["main", "light", "fallback", "dev"]


class ExecutionRecord(_Modele):
    """Un appel LLM (L1 5.7) : une ligne de runs/<run_id>/calls.jsonl, jamais de clé d'API."""

    appel_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    horodatage: AwareDatetime
    agent: str = Field(min_length=1)
    tier: TierEffectif
    mode: ModeExecution
    modele_demande: str
    modele_servi: str  # lu dans la réponse du fournisseur
    fin_entrainement_modele: date | None = None
    fournisseur: str
    relais_utilise: bool = False
    prompt_id: str
    prompt_version: str
    prompt_sha256: str
    cle_cache: str
    cache_hit: bool
    graine: int
    temperature: float = Field(ge=0)
    tokens_entree: int = Field(ge=0)
    tokens_sortie: int = Field(ge=0)
    cout_eur: float = Field(ge=0)
    cout_equivalent_payant_eur: float | None = Field(default=None, ge=0)
    latence_ms: int = Field(ge=0)
    erreur: str | None = None
    date_donnees: date

    @field_validator("prompt_sha256", "cle_cache")
    @classmethod
    def _hex64(cls, v: str) -> str:
        if not _SHA256.fullmatch(v):
            raise ValueError("SHA-256 hexadécimal (64 caractères) attendu")
        return v

    @model_validator(mode="after")
    def _evaluation_sans_relais(self) -> ExecutionRecord:
        if self.mode == "evaluation" and self.relais_utilise:
            raise ValueError("aucun relais en mode évaluation (D-024)")
        return self


class RunRecord(_Modele):
    """Un run complet (L1 5.7)."""

    run_id: str = Field(min_length=1)
    debut: AwareDatetime
    fin: AwareDatetime | None = None
    commande: str
    git_commit: str
    uv_lock_sha256: str
    config_sha256: str
    preregistration_sha256: str | None = None
    modele_servi_fige: str | None = None
    graine: int
    mode: ModeExecution
    avertissement: str

    @model_validator(mode="after")
    def _preenregistrement_en_evaluation(self) -> RunRecord:
        if self.mode == "evaluation" and not self.preregistration_sha256:
            raise ValueError("pré-enregistrement obligatoire en mode évaluation (EX-O5-12)")
        if self.fin is not None and self.fin < self.debut:
            raise ValueError("fin antérieure au début")
        return self
