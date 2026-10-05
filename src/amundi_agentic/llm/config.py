"""Lecture et validation de `config/llm.yaml` (C1, D-008, D-024).

Aucun nom de modèle ni de fournisseur dans le code : tout vient de ce fichier. Les clés d'API ne
sont jamais lues ici ; la config ne nomme que des variables d'environnement.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(os.environ.get("AMUNDI_CONFIG_DIR", ROOT / "config")) / "llm.yaml"

Profil = Literal["dev", "prod"]


class ConfigurationError(ValueError):
    """Configuration LLM invalide ou incomplète."""


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderCfg(_Cfg):
    api_key_env: str | None = None
    api_base_env: str | None = None


class EvaluationCfg(_Cfg):
    fallback_enabled: bool
    models: dict[str, str]


class DefaultsCfg(_Cfg):
    temperature: float = Field(ge=0)
    seed: int = 0
    timeout_s: float = Field(default=120, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    structured_retries: int = Field(default=2, ge=0)


class CacheCfg(_Cfg):
    enabled: bool = True
    dir: str = ".cache/llm"


class RetryCfg(_Cfg):
    max_attempts: int = Field(default=4, ge=1)
    backoff_base_s: float = Field(default=2, ge=0)
    backoff_factor: float = Field(default=2, ge=1)
    backoff_max_s: float = Field(default=60, ge=0)
    pause_429_wait_s: float = Field(default=65, ge=0)
    pause_429_max_waits: int = Field(default=2, ge=0)


class RelayCfg(_Cfg):
    cooldown_s: float = Field(default=60, ge=0)
    on_unavailable_exhausted: bool = True


class LimitCfg(_Cfg):
    requests_per_day: int | None = Field(default=None, gt=0)
    requests_per_minute: int | None = Field(default=None, gt=0)
    tokens_per_minute: int | None = Field(default=None, gt=0)


class QuotasCfg(_Cfg):
    alert_threshold: float = Field(default=0.8, gt=0, le=1)
    day_timezone: str = "UTC"
    journal: str = ".cache/llm/quotas.json"
    limits: dict[str, LimitCfg] = Field(default_factory=dict)


class PriceCfg(_Cfg):
    input_eur_per_mtok: float = Field(default=0, ge=0)
    output_eur_per_mtok: float = Field(default=0, ge=0)


class LLMConfig(_Cfg):
    providers: dict[str, ProviderCfg]
    models: dict[str, str]
    fallback_order: dict[str, list[str]] = Field(default_factory=dict)
    evaluation: EvaluationCfg
    default_mode: Profil = "dev"
    defaults: DefaultsCfg
    cache: CacheCfg = CacheCfg()
    retry: RetryCfg = RetryCfg()
    relay: RelayCfg = RelayCfg()
    quotas: QuotasCfg = QuotasCfg()
    pricing: dict[str, PriceCfg] = Field(default_factory=dict)
    embeddings: dict[str, str] = Field(default_factory=dict)
    training_cutoff: dict[str, date] = Field(default_factory=dict)
    # SHA-256 de la configuration effective (rempli par `load_config`, absent du fichier).
    source_sha256: str | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _coherence(self) -> LLMConfig:
        for ident in [
            *self.models.values(),
            *self.evaluation.models.values(),
            *self.embeddings.values(),
        ]:
            if "/" not in ident or ident.split("/", 1)[0] not in self.providers:
                raise ValueError(f"identifiant {ident!r} : fournisseur absent de `providers`")
        for niveau, chaine in self.fallback_order.items():
            if niveau not in self.models or not set(chaine) <= set(self.models):
                raise ValueError(f"fallback_order.{niveau} cite un niveau non déclaré")
        if self.evaluation.fallback_enabled:
            raise ValueError("le mode évaluation n'admet aucun relais (D-024)")
        interactifs = set(self.models.values())
        for niveau, ident in self.evaluation.models.items():
            if niveau not in self.models:
                raise ValueError(f"evaluation.models.{niveau} : niveau inconnu")
            if "latest" in ident.lower():
                raise ValueError(f"evaluation.models.{niveau} : version figée exigée (D-024)")
            if ident in interactifs:
                raise ValueError(
                    f"evaluation.models.{niveau} coïncide avec un identifiant de `models` : "
                    "le mode évaluation exige des modèles distincts du mode interactif (D-024)"
                )
        return self

    # ------------------------------------------------------------------ résolution

    def chain(self, tier: str, *, mode: str, profile: Profil) -> list[tuple[str, str]]:
        """Chaîne ordonnée [(niveau effectif, identifiant de modèle)] pour une demande.

        - profil `dev` : un seul modèle (le niveau `dev`), jamais de relais ;
        - mode `evaluation` : un seul modèle à version figée, jamais de relais (D-024) ;
        - mode `interactif` : `fallback_order[tier]`, ou le seul niveau demandé s'il n'y figure pas.
        """
        if tier not in self.models:
            raise ConfigurationError(f"niveau {tier!r} inconnu (niveaux : {sorted(self.models)})")
        if profile == "dev":
            return [("dev", self.models["dev"])]
        if mode == "evaluation":
            if tier not in self.evaluation.models:
                raise ConfigurationError(
                    f"pas de modèle figé pour le niveau {tier!r} en évaluation"
                )
            return [(tier, self.evaluation.models[tier])]
        niveaux = self.fallback_order.get(tier, [tier])
        return [(n, self.models[n]) for n in niveaux]

    def embedding_model(self, profile: Profil) -> str:
        try:
            return self.embeddings[profile]
        except KeyError:
            raise ConfigurationError(
                f"aucun modèle d'embedding pour le profil {profile!r}"
            ) from None

    def limits_for(self, provider: str, model: str) -> LimitCfg:
        limites = self.quotas.limits
        return limites.get(model) or limites.get(provider) or LimitCfg()


def load_config(path: Path | None = None, overrides: dict[str, Any] | None = None) -> LLMConfig:
    """Charge `config/llm.yaml` ; `overrides` (fusion superficielle par section) sert aux tests."""
    fichier = path or CONFIG_PATH
    octets = fichier.read_bytes()
    brut = yaml.safe_load(octets.decode("utf-8"))
    for section, valeur in (overrides or {}).items():
        if isinstance(valeur, dict) and isinstance(brut.get(section), dict):
            brut[section] = {**brut[section], **valeur}
        else:
            brut[section] = valeur
    try:
        config = LLMConfig.model_validate(brut)
    except ValidationError as exc:
        raise ConfigurationError(str(exc)) from None
    sans_surcharge = not overrides
    config.source_sha256 = (
        hashlib.sha256(octets).hexdigest()
        if sans_surcharge
        else hashlib.sha256(
            json.dumps(brut, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    )
    return config


def resolve_path(chemin: str | Path) -> Path:
    p = Path(chemin)
    return p if p.is_absolute() else ROOT / p
