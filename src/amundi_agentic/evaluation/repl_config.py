# ruff: noqa: E501, N806, N818
"""Lecture et validation de `config/replication.yaml` (protocole D-065).

Aucune valeur du protocole n'est codée ici : une clé absente est une erreur. Le fichier est lu en
octets pour son SHA-256 (le pré-enregistrement recopie aussi son contenu analysé).
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from amundi_agentic.data.settings import CONFIG_DIR

FICHIER = "replication.yaml"


class ConfigReplicationError(ValueError):
    """`replication.yaml` invalide ou incomplet."""


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProtocoleCfg(_Cfg):
    nom: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")
    reference: str


class CibleCfg(_Cfg):
    date_decision: date
    fin_suivi: date
    as_of_performance: date
    prix_entree: Literal["premiere_cloture_a_partir_de_t"]
    devise_performance: str
    prix: Literal["adj_close", "close"]
    rebalancement: Literal["unique"]
    couts_de_transaction: Literal["non_modelises"]

    @model_validator(mode="after")
    def _dates(self) -> CibleCfg:
        if not self.date_decision < self.fin_suivi:
            raise ValueError("date_decision doit précéder fin_suivi")
        if not self.as_of_performance > self.fin_suivi:
            raise ValueError(
                "as_of_performance doit suivre fin_suivi (les prix sont servis < as_of)"
            )
        return self


class PoolCfg(_Cfg):
    titre_hors_pool: str
    barres_min_historique: int = Field(ge=2)
    barres_min_janvier: int = Field(ge=1)
    depot_requis_avant_t: bool
    formulaires: list[str]
    titre_sans_prix_en_fin_de_suivi: Literal["derniere_valeur_connue"]
    depots_texte_requis: bool


class TirageCfg(_Cfg):
    n_titres: int = Field(ge=1)
    graine: int
    methode: Literal["tri_par_sha256"]
    remplacement: Literal["titre_suivant_dans_la_permutation"]
    n_tirages_secondaires: int = Field(ge=0)
    graine_secondaires: int


class EvaluationCfg(_Cfg):
    agents_votants: list[str]
    inclure_sentiment: bool
    journal_complet: bool

    @model_validator(mode="after")
    def _sans_sentiment(self) -> EvaluationCfg:
        if self.inclure_sentiment or "sentiment" in self.agents_votants:
            raise ValueError("l'agent Sentiment est exclu de la réplication (D-044)")
        return self


class ExecutionCfg(_Cfg):
    nom: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    temperature: float = Field(ge=0)
    paraphrase: str | None
    graine_llm: int


class ParaphrasesCfg(_Cfg):
    dossier: str
    prompts_paraphrases: list[str]


class MappingCfg(_Cfg):
    buy_si_niveau_superieur_a: int
    abstention: Literal["exclu_des_portefeuilles_signal"]
    sensibilite_abstention_buy: bool
    portefeuille_vide: Literal["tresorerie"]


class TauxSansRisqueCfg(_Cfg):
    serie: str
    mode: Literal["moyenne_sur_la_fenetre"]
    tresorerie: Literal["taux_du_jour_reporte"]


class PerformanceCfg(_Cfg):
    fenetre_sharpe_glissant: int = Field(ge=2)


class DistributionCfg(_Cfg):
    max_exact: int = Field(ge=1)
    n_echantillon: int = Field(ge=1)
    graine: int


class BootstrapCfg(_Cfg):
    methode: Literal["stationnaire"]
    longueur_moyenne_bloc: float = Field(ge=1)
    n_reechantillonnages: int = Field(ge=1)
    graine: int
    niveau: float = Field(gt=0, lt=1)


class InferenceCfg(_Cfg):
    bootstrap: BootstrapCfg
    wilson_niveau: float = Field(gt=0, lt=1)


class ReglesRapportCfg(_Cfg):
    min_titres_differents: int = Field(ge=1)
    desaccord_entre_executions: Literal["ecart_type"]
    regle_a_battre: Literal["ET"]
    comparaisons_agents_seuls: list[str]
    profils_requis: Literal["tous"]
    jamais_de_moyenne_entre_modeles: bool


class ModeleCfg(_Cfg):
    marge_contamination_mois: int = Field(ge=0)
    etiquette_contamine: str
    etiquette_hors_echantillon: str
    etiquette_marge: str
    etiquette_inconnue: str
    etiquette_simule: str


class RapportInterditCfg(_Cfg):
    motifs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _regex(self) -> RapportInterditCfg:
        import re

        for m in self.motifs:
            re.compile(m)
        return self


class CoutCfg(_Cfg):
    secondes_par_appel: float | None = Field(default=None, gt=0)


class ReplicationConfig(_Cfg):
    protocole: ProtocoleCfg
    cible: CibleCfg
    profils: list[str] = Field(min_length=1)
    pool: PoolCfg
    tirage: TirageCfg
    evaluation: EvaluationCfg
    executions: list[ExecutionCfg] = Field(min_length=1)
    paraphrases: ParaphrasesCfg
    mapping: MappingCfg
    taux_sans_risque: TauxSansRisqueCfg
    performance: PerformanceCfg
    distribution_aleatoire: DistributionCfg
    inference: InferenceCfg
    regles_rapport: ReglesRapportCfg
    modele: ModeleCfg
    rapport_interdit: RapportInterditCfg
    cout: CoutCfg
    # rempli par `charger_config` (hors fichier)
    source_sha256: str | None = Field(default=None, exclude=True)
    chemin: Path | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _coherence(self) -> ReplicationConfig:
        noms = [e.nom for e in self.executions]
        if len(set(noms)) != len(noms):
            raise ValueError("noms d'exécutions en double")
        if "baseline" not in noms:
            raise ValueError("une exécution `baseline` est exigée (référence du verdict)")
        for e in self.executions:
            if e.paraphrase is not None and e.temperature != 0:
                raise ValueError("une paraphrase se mesure à température 0 (D-065 §7)")
        if len(set(self.profils)) != len(self.profils):
            raise ValueError("profils en double")
        return self

    def execution(self, nom: str) -> ExecutionCfg:
        for e in self.executions:
            if e.nom == nom:
                return e
        raise KeyError(nom)


def charger_config(
    path: Path | None = None, overrides: dict[str, Any] | None = None
) -> ReplicationConfig:
    """Charge et valide le protocole. `overrides` (fusion récursive) sert aux tests : le hash est
    alors celui du contenu fusionné, pas du fichier."""
    fichier = path or CONFIG_DIR / FICHIER
    octets = fichier.read_bytes()
    brut = yaml.safe_load(octets.decode("utf-8"))
    if overrides:
        brut = _fusion(brut, overrides)
    try:
        cfg = ReplicationConfig.model_validate(brut)
    except ValidationError as exc:
        raise ConfigReplicationError(f"{fichier.name} invalide : {exc}") from None
    cfg.source_sha256 = (
        hashlib.sha256(octets).hexdigest()
        if not overrides
        else hashlib.sha256(repr(sorted(_aplatir(brut).items())).encode()).hexdigest()
    )
    cfg.chemin = fichier
    return cfg


def _fusion(base: dict, sur: dict) -> dict:
    sortie = dict(base)
    for k, v in sur.items():
        sortie[k] = (
            _fusion(sortie[k], v) if isinstance(v, dict) and isinstance(sortie.get(k), dict) else v
        )
    return sortie


def _aplatir(d: Any, prefixe: str = "") -> dict[str, Any]:
    """Dictionnaire aplati `a.b.c -> valeur` (les listes sont des feuilles) : sert au hash fusionné
    et au détail des écarts du pré-enregistrement."""
    if isinstance(d, dict):
        sortie: dict[str, Any] = {}
        for k, v in d.items():
            sortie.update(_aplatir(v, f"{prefixe}.{k}" if prefixe else str(k)))
        return sortie
    return {prefixe: d}


def aplatir(d: Any) -> dict[str, Any]:
    return _aplatir(d)
