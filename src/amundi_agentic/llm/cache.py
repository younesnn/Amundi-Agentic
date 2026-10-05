"""Cache disque des réponses (EX-NF-04) : une requête identique ne part jamais deux fois.

Clé = SHA-256 de (type d'appel, modèle demandé, messages, schéma, paramètres, `date_donnees`).
Aucune clé d'API n'entre dans la clé ni dans les fichiers. Écriture atomique : un fichier est
complet ou absent, ce qui permet la reprise après interruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


def cache_key(
    *,
    kind: str,
    model: str,
    messages: list[dict[str, str]] | list[str],
    schema: dict[str, Any] | None,
    params: dict[str, Any],
    date_donnees: date,
    scope: str = "",
) -> str:
    charge = {
        "kind": kind,
        "model": model,
        "messages": messages,
        "schema": schema,
        "params": params,
        "date_donnees": date_donnees.isoformat(),
        # Cloisonnement par mode et profil : une entrée interactive ou dev n'est jamais servie
        # à une exécution d'évaluation (EX-NF-13).
        "scope": scope,
    }
    brut = json.dumps(charge, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


class DiskCache:
    def __init__(self, directory: Path, enabled: bool = True) -> None:
        self.directory = directory
        self.enabled = enabled

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        chemin = self._path(key)
        try:
            entree = json.loads(chemin.read_text(encoding="utf-8"))
            # Une entrée valide mais d'une autre forme (liste, nombre) est traitée comme absente.
            return entree if isinstance(entree, dict) else None
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            # Entrée corrompue (écriture interrompue d'un autre outil) : traitée comme absente.
            return None

    def put(self, key: str, entry: dict[str, Any]) -> None:
        if not self.enabled:
            return
        chemin = self._path(key)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, chemin)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
