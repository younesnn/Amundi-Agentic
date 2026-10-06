"""Simulation déterministe du LLM : la suite de tests passe sans clé ni réseau (EX-NF-12).

`MockTransport` remplace LiteLLM sous le vrai `LLMClient` : relais, nouvelles tentatives, cache,
quotas et mode évaluation s'exécutent donc réellement, seul l'appel réseau est simulé.
`MockLLMClient` est un `LLMClient` prêt à l'emploi (cache et journaux dans un dossier
temporaire, attentes simulées).
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from amundi_agentic.llm.client import LLMClient
from amundi_agentic.llm.config import LLMConfig
from amundi_agentic.llm.types import (
    ErrorKind,
    ProviderError,
    RawCompletion,
    RawEmbedding,
    Transport,
)

Item = str | ProviderError | RawCompletion
Handler = Callable[[str, list[dict[str, str]]], str]


def quota_error(message: str = "429 simulé") -> ProviderError:
    return ProviderError("quota", message, 429)


def unavailable_error(message: str = "503 simulé") -> ProviderError:
    return ProviderError("unavailable", message, 503)


def timeout_error(message: str = "timeout simulé") -> ProviderError:
    return ProviderError("timeout", message)


class MockTransport(Transport):
    """Réponses scriptées (file d'attente, éventuellement par modèle), sinon `handler`, sinon
    `default_text`. Les appels sont conservés dans `calls`."""

    def __init__(
        self,
        responses: Sequence[Item] = (),
        *,
        handler: Handler | None = None,
        default_text: str = "{}",
    ) -> None:
        self._queue: list[tuple[str | None, Item]] = [(None, r) for r in responses]
        self.handler = handler
        self.default_text = default_text
        self.served: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    # --- scénarios

    def push(self, *items: Item, model: str | None = None) -> MockTransport:
        """Ajoute des réponses (texte, `ProviderError` à lever, ou `RawCompletion`) ; avec
        `model`, elles ne servent que pour ce modèle."""
        self._queue.extend((model, i) for i in items)
        return self

    def fail(self, kind: ErrorKind, times: int = 1, *, model: str | None = None) -> MockTransport:
        """Injecte `times` échecs 429 (`quota`), 503 (`unavailable`) ou timeout."""
        fabriques = {
            "quota": quota_error,
            "unavailable": unavailable_error,
            "timeout": timeout_error,
        }
        return self.push(*[fabriques[kind]() for _ in range(times)], model=model)

    def invalid_json(self, times: int = 1, *, model: str | None = None) -> MockTransport:
        return self.push(*["ceci n'est pas du JSON"] * times, model=model)

    def set_served(self, model: str, served: str) -> None:
        """Identifiant que le « fournisseur » renverra pour ce modèle (simule une dérive)."""
        self.served[model] = served

    # --- Transport

    def _servi(self, model: str) -> str:
        return self.served.get(model, model.split("/", 1)[-1])

    def _suivant(self, model: str) -> Item | None:
        for i, (cible, item) in enumerate(self._queue):
            if cible is None or cible == model:
                del self._queue[i]
                return item
        return None

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
        extra_params: dict[str, Any] | None = None,
    ) -> RawCompletion:
        self.calls.append(
            {
                "extra_params": dict(extra_params or {}),
                "kind": "chat",
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "seed": seed,
                "json_mode": json_mode,
            }
        )
        item = self._suivant(model)
        if isinstance(item, ProviderError):
            raise item
        if isinstance(item, RawCompletion):
            return item
        texte = (
            item
            if item is not None
            else (self.handler(model, messages) if self.handler else self.default_text)
        )
        taille_entree = sum(len(m["content"]) for m in messages)
        return RawCompletion(texte, self._servi(model), taille_entree // 4 + 1, len(texte) // 4 + 1)

    def embedding(self, *, model: str, inputs: list[str], timeout: float) -> RawEmbedding:
        self.calls.append({"kind": "embed", "model": model, "inputs": inputs})
        item = self._suivant(model)
        if isinstance(item, ProviderError):
            raise item
        vecteurs = [
            [b / 255 for b in hashlib.sha256(t.encode("utf-8")).digest()[:8]] for t in inputs
        ]
        return RawEmbedding(vecteurs, self._servi(model), sum(len(t) for t in inputs) // 4 + 1)

    @property
    def chat_calls(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["kind"] == "chat"]


class MockLLMClient(LLMClient):
    """`LLMClient` sur `MockTransport` : aucun accès réseau, aucune écriture hors dossier
    temporaire (sauf `cache_dir`, `run_dir` et `quota_journal` explicites), attentes simulées
    (relevées dans `sleeps`)."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        *,
        transport: MockTransport | None = None,
        responses: Sequence[Item] = (),
        handler: Handler | None = None,
        default_text: str = "{}",
        cache_dir: Path | str | None = None,
        quota_journal: Path | str | None = None,
        **kwargs: Any,
    ) -> None:
        self.mock = transport or MockTransport(
            responses, handler=handler, default_text=default_text
        )
        self.sleeps: list[float] = []
        racine = Path(tempfile.mkdtemp(prefix="amundi-llm-mock-"))
        kwargs.setdefault("sleep", self.sleeps.append)
        super().__init__(
            config,
            transport=self.mock,
            cache_dir=cache_dir or racine / "cache",
            quota_journal=quota_journal or racine / "quotas.json",
            **kwargs,
        )
