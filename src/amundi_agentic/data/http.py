"""Client HTTP avec cache disque, limitation de débit par source, reprise et backoff.

- Cache : une requête identique (méthode, URL, paramètres hors secrets) n'est jamais renvoyée
  sur le réseau ; la clé de cache et les métadonnées ne contiennent aucun secret.
- Débit : intervalle minimal entre deux requêtes d'une même source (config/data.yaml).
- Backoff : 429 et 5xx (et erreurs réseau) sont rejoués avec attente exponentielle plus gigue ;
  l'en-tête Retry-After est respecté. La vérification TLS n'est jamais désactivée.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

SECRET_PARAMS = ("api_key", "apikey", "key", "token")
SECRET_ENV_VARS = ("FRED_API_KEY",)
_RETRY_STATUS = {429, 500, 502, 503, 504}
_PATTERN_SECRET = re.compile(r"(?i)\b(api_key|apikey|token)=[^&\s\"')]+")


class HttpError(RuntimeError):
    """Échec définitif d'une requête (message expurgé de tout secret)."""

    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body  # extrait de la réponse, expurgé de secrets


def redact(text: str) -> str:
    """Retire des secrets d'un texte : motifs `api_key=...` et valeurs connues de l'environnement."""
    text = _PATTERN_SECRET.sub(lambda m: f"{m.group(1)}=***", text)
    for var in SECRET_ENV_VARS:
        val = os.environ.get(var)
        if val:
            text = text.replace(val, "***")
    return text


@dataclass(frozen=True)
class HttpResponse:
    status: int
    content: bytes
    url: str  # URL publique, sans secret
    from_cache: bool
    headers: Mapping[str, str]

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content)


class HttpClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        min_intervals: Mapping[str, float] | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
        max_attempts: int = 5,
        base_backoff_s: float = 2.0,
        max_backoff_s: float = 120.0,
        timeout_s: float = 30.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.min_intervals = dict(min_intervals or {})
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self.max_attempts = max_attempts
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self.timeout_s = timeout_s
        self._last_call: dict[str, float] = {}
        self.network_calls = 0

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _public_params(params: Mapping[str, Any] | None) -> dict[str, str]:
        return {
            k: str(v) for k, v in sorted((params or {}).items()) if k.lower() not in SECRET_PARAMS
        }

    def cache_key(self, url: str, params: Mapping[str, Any] | None = None) -> str:
        brut = json.dumps(
            {"url": redact(url), "params": self._public_params(params)}, sort_keys=True
        )
        return hashlib.sha256(brut.encode("utf-8")).hexdigest()

    def _paths(self, source: str, key: str) -> tuple[Path, Path]:
        d = self.cache_dir / source / key[:2]
        return d / f"{key}.bin", d / f"{key}.json"

    def _read_cache(self, source: str, key: str, ttl_s: float | None) -> HttpResponse | None:
        corps, meta = self._paths(source, key)
        if not (corps.is_file() and meta.is_file()):
            return None
        info = json.loads(meta.read_text(encoding="utf-8"))
        if ttl_s is not None:
            age = (datetime.now(UTC) - datetime.fromisoformat(info["fetched_at"])).total_seconds()
            if age > ttl_s:
                return None
        return HttpResponse(info["status"], corps.read_bytes(), info["url"], True, info["headers"])

    def _write_cache(self, source: str, key: str, resp: HttpResponse) -> None:
        corps, meta = self._paths(source, key)
        corps.parent.mkdir(parents=True, exist_ok=True)
        tmp = corps.with_name(corps.name + f".tmp{os.getpid()}")
        tmp.write_bytes(resp.content)
        os.replace(tmp, corps)
        info = {
            "url": resp.url,
            "status": resp.status,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "headers": {k: v for k, v in resp.headers.items() if k.lower() == "content-type"},
        }
        meta.write_text(json.dumps(info), encoding="utf-8")

    # ------------------------------------------------------------------ débit et backoff
    def _throttle(self, source: str) -> None:
        mini = self.min_intervals.get(source, 0.0)
        dernier = self._last_call.get(source)
        if mini and dernier is not None:
            attente = mini - (self._clock() - dernier)
            if attente > 0:
                self._sleep(attente)
        self._last_call[source] = self._clock()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.strip().isdigit():
            return min(float(retry_after), self.max_backoff_s)
        return min(self.base_backoff_s * 2**attempt, self.max_backoff_s) + self._jitter()

    def get(
        self,
        source: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        ttl_s: float | None = None,
        refresh: bool = False,
        validate: Callable[[bytes], bool] | None = None,
    ) -> HttpResponse:
        """GET avec cache. `ttl_s=None` : le cache n'expire jamais (reproductibilité)."""
        key = self.cache_key(url, params)
        if not refresh:
            en_cache = self._read_cache(source, key, ttl_s)
            if en_cache is not None:
                return en_cache
        public_url = redact(url) + (
            "?" + "&".join(f"{k}={v}" for k, v in self._public_params(params).items())
            if params
            else ""
        )
        derniere_erreur = "aucune tentative"
        statut: int | None = None
        for tentative in range(self.max_attempts):
            self._throttle(source)
            self.network_calls += 1
            retry_after = None
            try:
                r = self.session.get(
                    url, params=params, headers=dict(headers or {}), timeout=self.timeout_s
                )
            except requests.RequestException as exc:  # pas de désactivation de TLS, jamais
                derniere_erreur = redact(f"{type(exc).__name__}: {exc}")
                statut = None
            else:
                statut = r.status_code
                if r.status_code == 200:
                    resp = HttpResponse(200, r.content, public_url, False, dict(r.headers))
                    if validate is None or validate(resp.content):
                        self._write_cache(source, key, resp)  # un corps invalide n'est jamais caché
                    return resp
                derniere_erreur = f"HTTP {r.status_code}"
                if r.status_code not in _RETRY_STATUS:
                    raise HttpError(
                        f"{source} {public_url} : {derniere_erreur}",
                        r.status_code,
                        redact(r.text[:300]),
                    )
                retry_after = r.headers.get("Retry-After")
            if tentative < self.max_attempts - 1:
                attente = self._backoff(tentative, retry_after)
                log.warning("%s : %s, nouvel essai dans %.1f s", source, derniere_erreur, attente)
                self._sleep(attente)
        raise HttpError(
            f"{source} {public_url} : échec après {self.max_attempts} essais ({derniere_erreur})",
            statut,
        )
