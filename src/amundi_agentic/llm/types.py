"""Types d'échange du client LLM : messages, résultats, erreurs, interface de transport."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from amundi_agentic.schemas import ExecutionRecord

Tier = Literal["main", "light", "fallback", "dev"]
ErrorKind = Literal["quota", "unavailable", "timeout", "auth", "bad_request", "other"]


class Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class PromptRef(BaseModel):
    """Prompt de rôle versionné (EX-O1-06) : identifiant, version et SHA-256 du fichier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_id: str
    version: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def sha256_text(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RawCompletion:
    """Réponse brute d'un transport."""

    text: str
    model_served: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(frozen=True)
class RawEmbedding:
    vectors: list[list[float]]
    model_served: str
    tokens_in: int = 0


@dataclass
class LLMResult:
    """Résultat de `complete` : texte brut, objet validé (si schéma) et enregistrement.

    `record` est l'enregistrement de l'appel qui a produit la réponse retenue ; `attempts`
    contient aussi les tentatives invalides précédentes (sortie structurée).
    """

    text: str
    parsed: BaseModel | None
    record: ExecutionRecord
    attempts: list[ExecutionRecord] = field(default_factory=list)


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    record: ExecutionRecord


# --------------------------------------------------------------------------- erreurs


class LLMError(Exception):
    """Racine des erreurs du client. Les messages ne contiennent jamais de clé d'API."""


class ProviderError(LLMError):
    """Erreur d'un fournisseur, classée pour décider du relais ou de la reprise."""

    def __init__(self, kind: ErrorKind, message: str = "", status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


class QuotaEpuise(LLMError):  # noqa: N818
    """Mode interactif : tous les modèles de la chaîne ont répondu 429 ou sont indisponibles."""


class ExecutionPausee(LLMError):  # noqa: N818
    """Mode évaluation : 429 ou 503 persistant. L'exécution s'arrête proprement ; relancer la
    même commande reprend depuis le cache (EX-NF-13)."""

    def __init__(self, raison: str, kind: str) -> None:
        super().__init__(raison)
        self.kind = kind


class ModeleServiChange(LLMError):  # noqa: N818
    """Mode évaluation : le modèle servi diffère du modèle figé du run (EX-NF-13)."""


class FichierFigeCorrompu(LLMError):  # noqa: N818
    """Mode évaluation : `modele_servi_fige.json` illisible ou de forme inattendue. L'exécution
    s'arrête : regeler sur une version quelconque ferait perdre la garantie EX-NF-13."""


class StructuredOutputError(LLMError):
    """Sortie non conforme au schéma après les nouvelles tentatives autorisées."""

    def __init__(self, message: str, last_text: str = "") -> None:
        super().__init__(message)
        self.last_text = last_text


class Transport:
    """Interface d'un transport (LiteLLM réel ou simulé). Lève `ProviderError`."""

    def completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        seed: int,
        max_tokens: int | None,
        timeout: float,
        json_mode: bool,
    ) -> RawCompletion:
        raise NotImplementedError

    def embedding(self, *, model: str, inputs: list[str], timeout: float) -> RawEmbedding:
        raise NotImplementedError
