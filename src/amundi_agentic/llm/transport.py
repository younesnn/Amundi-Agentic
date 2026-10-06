"""Transport réel : LiteLLM. Seul fichier du dépôt qui importe LiteLLM (L1 3.2, EX-NF-05).

Les clés sont lues dans l'environnement (variables nommées par `config/llm.yaml`) et passées à
LiteLLM en mémoire ; elles ne sont ni stockées ni affichées, et tout message d'erreur remonté est
masqué par `redact`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from amundi_agentic.llm.config import ROOT, ConfigurationError, LLMConfig
from amundi_agentic.llm.redact import redact
from amundi_agentic.llm.types import ProviderError, RawCompletion, RawEmbedding, Transport

log = logging.getLogger(__name__)


def load_dotenv(path: os.PathLike[str] | str | None = None) -> None:
    """Charge `.env` sans écraser l'environnement. Ne retourne ni n'affiche aucune valeur."""
    from pathlib import Path

    fichier = Path(path) if path else ROOT / ".env"
    if not fichier.is_file():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        valeur = valeur.strip().strip('"').strip("'")
        if valeur:
            os.environ.setdefault(cle.strip(), valeur)


def _jetons(valeur: Any) -> int:
    """Nombre de jetons d'un champ `usage` ; absent, non numérique, négatif ou NaN : 0
    (« inconnu », jamais une exception brute ni une preuve de troncature, D-062)."""
    if isinstance(valeur, bool) or not isinstance(valeur, int | float):
        return 0
    return int(valeur) if 0 <= valeur < 10**12 else 0


def _classify(exc: BaseException) -> ProviderError:
    """Traduit une exception LiteLLM en `ProviderError` (statut HTTP d'abord, puis classe)."""
    nom = type(exc).__name__
    statut = getattr(exc, "status_code", None)
    message = redact(f"{nom}: {exc}")[:500]
    if statut == 429 or nom == "RateLimitError":
        return ProviderError("quota", message, 429)
    if statut in (500, 502, 503, 504) or nom in {
        "ServiceUnavailableError",
        "InternalServerError",
        "BadGatewayError",
    }:
        return ProviderError("unavailable", message, statut)
    if nom in {"Timeout", "APITimeoutError", "APIConnectionError"} or isinstance(
        exc, TimeoutError | ConnectionError
    ):
        return ProviderError("timeout", message, statut)
    if statut in (401, 403) or nom in {"AuthenticationError", "PermissionDeniedError"}:
        return ProviderError("auth", message, statut)
    if statut in (400, 404, 422) or nom in {
        "BadRequestError",
        "NotFoundError",
        "ContextWindowExceededError",
        "UnprocessableEntityError",
    }:
        return ProviderError("bad_request", message, statut)
    return ProviderError("other", message, statut)


class LiteLLMTransport(Transport):
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        load_dotenv()
        # Pas de requête réseau à l'import : table de coûts locale.
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        self._litellm: Any = None

    def _lib(self) -> Any:
        if self._litellm is None:
            import litellm

            litellm.suppress_debug_info = True
            litellm.drop_params = True  # paramètre non géré par un fournisseur : ignoré
            litellm.telemetry = False
            logging.getLogger("LiteLLM").setLevel(logging.WARNING)
            self._litellm = litellm
        return self._litellm

    def _credentials(self, model: str) -> dict[str, str]:
        fournisseur = model.split("/", 1)[0]
        cfg = self._config.providers[fournisseur]
        kwargs: dict[str, str] = {}
        if cfg.api_key_env:
            cle = os.environ.get(cfg.api_key_env, "")
            if not cle:
                raise ConfigurationError(
                    f"variable d'environnement {cfg.api_key_env} absente (voir .env.example)"
                )
            kwargs["api_key"] = cle
        if cfg.api_base_env and os.environ.get(cfg.api_base_env):
            kwargs["api_base"] = os.environ[cfg.api_base_env]
        return kwargs

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
        lib = self._lib()
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "seed": seed,
            "timeout": timeout,
            "num_retries": 0,  # les nouvelles tentatives sont gérées par LLMClient
            **self._credentials(model),
        }
        # Paramètres propres au fournisseur (ex. `num_ctx` Ollama : LiteLLM le range dans
        # `options` de la requête). Jamais écrasés par les paramètres communs.
        for k, v in (extra_params or {}).items():
            params.setdefault(k, v)
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        try:
            reponse = lib.completion(**params)
        except Exception as exc:
            raise _classify(exc) from None
        try:
            texte = reponse.choices[0].message.content or ""
            usage = getattr(reponse, "usage", None)
            return RawCompletion(
                text=texte,
                model_served=str(getattr(reponse, "model", "") or ""),
                tokens_in=_jetons(getattr(usage, "prompt_tokens", None)),
                tokens_out=_jetons(getattr(usage, "completion_tokens", None)),
            )
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderError("other", redact(f"réponse inattendue : {exc}")) from None

    def embedding(self, *, model: str, inputs: list[str], timeout: float) -> RawEmbedding:
        lib = self._lib()
        try:
            reponse = lib.embedding(
                model=model, input=inputs, timeout=timeout, **self._credentials(model)
            )
        except Exception as exc:
            raise _classify(exc) from None
        try:
            donnees = sorted(reponse.data, key=lambda d: d["index"])
            usage = getattr(reponse, "usage", None)
            return RawEmbedding(
                vectors=[list(map(float, d["embedding"])) for d in donnees],
                model_served=str(getattr(reponse, "model", "") or ""),
                tokens_in=_jetons(getattr(usage, "prompt_tokens", None)),
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProviderError("other", redact(f"réponse inattendue : {exc}")) from None
