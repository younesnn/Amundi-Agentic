"""Lecture de `config/debate.yaml` : paramètres du débat, de la confiance, du risque et des agents.

Aucune valeur par défaut n'est codée ici (L1 §6.4, D-016) : un champ absent du fichier est une erreur,
pour qu'aucune hypothèse (H) ne vive dans le code. Le fichier est lu par `agents/` et par `debate/`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from amundi_agentic.data.settings import CONFIG_DIR
from amundi_agentic.schemas import DebateConfig

FICHIER = "debate.yaml"


class SettingsError(ValueError):
    """Configuration du débat invalide ou incomplète."""


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DebateCfg(_Cfg):
    r_max: int = Field(ge=0)
    graine_rotation: int
    ordre_round_robin: dict[str, list[str]]
    sentiment_vote_en_live_seulement: bool
    orchestrateur: Literal["langgraph", "boucle"]
    max_titres: int = Field(ge=1)
    horizon_mois: int = Field(ge=1, le=12)
    actif_neutre_transmis: bool
    transmettre_voix_unique: bool

    @model_validator(mode="after")
    def _niveaux(self) -> DebateCfg:
        if set(self.ordre_round_robin) != {"allocation", "titre"}:
            raise ValueError("ordre_round_robin : niveaux `allocation` et `titre` exigés")
        return self


class ConsensusCfg(_Cfg):
    ecart_consensus_large: int = Field(ge=1)
    ecart_contestee_min: int = Field(ge=2)
    borne_contestee: int = Field(ge=0, le=2)
    min_votants_valides: int = Field(ge=1)

    @model_validator(mode="after")
    def _coherence(self) -> ConsensusCfg:
        if self.ecart_contestee_min != self.ecart_consensus_large + 1:
            raise ValueError(
                "ecart_contestee_min doit valoir ecart_consensus_large + 1 (aucun écart sans statut)"
            )
        return self


class ConfidenceCfg(_Cfg):
    c_max: float = Field(gt=0, lt=1)
    c_min: float = Field(ge=0)
    g: dict[str, float]
    rho_par_tour: float = Field(ge=0)
    plafond_voix_unique: float = Field(ge=0, le=1)
    h: dict[str, float]
    alerte_si_indisponible: Literal["aucune", "moderee", "elevee"]

    @model_validator(mode="after")
    def _coherence(self) -> ConfidenceCfg:
        if self.c_min > self.c_max:
            raise ValueError("c_min <= c_max exigé")
        if set(self.g) != {"unanime", "consensus", "contestee"}:
            raise ValueError("g : clés unanime, consensus, contestee exigées")
        if set(self.h) != {"aucune", "moderee", "elevee"}:
            raise ValueError("h : clés aucune, moderee, elevee exigées")
        for v in [*self.g.values(), *self.h.values()]:
            if not 0 <= v <= 1:
                raise ValueError("g et h sont des facteurs dans [0, 1]")
        return self


class RiskCfg(_Cfg):
    seuils: dict[str, float]
    default_replay_weeks: int = Field(ge=0)
    regime_reference_class: str
    vix_series: str
    commenter_titres: bool
    alerte_titre: Literal["propre", "classe"]


class GroundingCfg(_Cfg):
    max_retries: int = Field(ge=0)
    tolerance_relative_entiers: float = Field(ge=0, le=0.5)
    facteurs_echelle: list[float]
    facteur_points_de_base: float
    plage_annees: tuple[int, int]
    fenetre_contexte_mots: int = Field(ge=1)
    contexte_financier: list[str]
    unites_financieres: list[str]


class ValuationCfg(_Cfg):
    fenetre_seances: int = Field(ge=2)


class FundamentalCfg(_Cfg):
    rag_k: int = Field(ge=1)
    max_caracteres_passage: int = Field(ge=100)
    questions: list[str] = Field(min_length=1)
    concepts_xbrl_max: int = Field(ge=0)
    plafond_confiance_decoupage_echoue: float = Field(ge=0, le=1)


class SentimentCfg(_Cfg):
    fenetre_jours: int = Field(ge=1)
    max_articles: int = Field(ge=1)
    reflexion_tours: int = Field(ge=0)
    termes_allocation: list[str]
    focus_allocation: str
    focus_titre: str


class EsgCfg(_Cfg):
    etf_criteres_requis: list[str]
    etf_etats_acceptes: list[str]
    llm_explique_les_vetos: bool
    accepter_non_point_in_time: dict[str, bool]

    @model_validator(mode="after")
    def _modes(self) -> EsgCfg:
        if set(self.accepter_non_point_in_time) != {"interactif", "evaluation"}:
            raise ValueError("accepter_non_point_in_time : clés interactif et evaluation")
        return self


class LimitesCfg(_Cfg):
    motif_max_caracteres: int = Field(ge=20)
    marge_recursion: int = Field(ge=1)


class DebateSettings(_Cfg):
    debate: DebateCfg
    consensus: ConsensusCfg
    confidence: ConfidenceCfg
    risk: RiskCfg
    grounding: GroundingCfg
    valuation: ValuationCfg
    fundamental: FundamentalCfg
    sentiment: SentimentCfg
    esg: EsgCfg
    limites: LimitesCfg
    source_sha256: str | None = Field(default=None, exclude=True)

    def debate_config(self) -> DebateConfig:
        """`DebateConfig` du journal (schemas.py) : R_max, graine, paramètres de confiance à plat."""
        c = self.confidence
        plat: dict[str, float] = {
            "c_max": c.c_max,
            "c_min": c.c_min,
            "rho_par_tour": c.rho_par_tour,
        }
        plat.update({f"g_{k}": v for k, v in c.g.items()})
        plat.update({f"h_{k}": v for k, v in c.h.items()})
        plat["ecart_consensus_large"] = float(self.consensus.ecart_consensus_large)
        plat["ecart_contestee_min"] = float(self.consensus.ecart_contestee_min)
        plat["borne_contestee"] = float(self.consensus.borne_contestee)
        plat["min_votants_valides"] = float(self.consensus.min_votants_valides)
        plat["plafond_voix_unique"] = c.plafond_voix_unique
        return DebateConfig(
            r_max=self.debate.r_max,
            parametres_confiance=plat,
            graine_rotation=self.debate.graine_rotation,
        )


def load_settings(path: Path | None = None, overrides: dict | None = None) -> DebateSettings:
    """Charge `config/debate.yaml` (ou `path`). `overrides` : fusion récursive, pour les tests."""
    fichier = path or CONFIG_DIR / FICHIER
    octets = fichier.read_bytes()
    brut = yaml.safe_load(octets.decode("utf-8"))
    if overrides:
        brut = _fusion(brut, overrides)
    try:
        s = DebateSettings.model_validate(brut)
    except ValidationError as exc:
        raise SettingsError(f"{fichier.name} invalide : {exc}") from None
    s.source_sha256 = hashlib.sha256(octets).hexdigest() if not overrides else None
    return s


def _fusion(base: dict, sur: dict) -> dict:
    sortie = dict(base)
    for k, v in sur.items():
        sortie[k] = (
            _fusion(sortie[k], v) if isinstance(v, dict) and isinstance(sortie.get(k), dict) else v
        )
    return sortie
