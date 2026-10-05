"""LLMClient unique (LiteLLM), seul module autorisé à importer LiteLLM ou un SDK de fournisseur.

Les modèles viennent de `config/llm.yaml` (C1, D-008) ; budget 0 € (D-004). Phase 3.
"""

from amundi_agentic.llm.client import LLMClient
from amundi_agentic.llm.config import ConfigurationError, LLMConfig, load_config
from amundi_agentic.llm.mock import MockLLMClient, MockTransport
from amundi_agentic.llm.types import (
    EmbeddingResult,
    ExecutionPausee,
    LLMError,
    LLMResult,
    Message,
    ModeleServiChange,
    PromptRef,
    ProviderError,
    QuotaEpuise,
    StructuredOutputError,
)

__all__ = [
    "ConfigurationError",
    "EmbeddingResult",
    "ExecutionPausee",
    "LLMClient",
    "LLMConfig",
    "LLMError",
    "LLMResult",
    "Message",
    "MockLLMClient",
    "MockTransport",
    "ModeleServiChange",
    "PromptRef",
    "ProviderError",
    "QuotaEpuise",
    "StructuredOutputError",
    "load_config",
]
