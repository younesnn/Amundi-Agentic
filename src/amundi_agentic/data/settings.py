"""Chemins, configuration et secrets. Les secrets ne sont jamais affichés ni écrits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from amundi_agentic.data.models import MissingSecretError

ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = Path(os.environ.get("AMUNDI_CONFIG_DIR", ROOT / "config"))


def load_dotenv(path: Path | None = None) -> None:
    """Charge `.env` sans écraser l'environnement. Ne retourne ni n'affiche aucune valeur."""
    fichier = path or ROOT / ".env"
    if not fichier.is_file():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        valeur = valeur.strip().strip('"').strip("'")
        if valeur:
            os.environ.setdefault(cle.strip(), valeur)


def require_secret(name: str) -> str:
    load_dotenv()
    valeur = os.environ.get(name, "")
    if not valeur:
        raise MissingSecretError(f"variable d'environnement {name} absente (voir .env.example)")
    return valeur


def load_yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class DataSettings:
    data_dir: Path
    config: dict[str, Any]

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "http"

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def store_dir(self) -> Path:
        return self.data_dir / "store"

    @classmethod
    def load(cls, data_dir: Path | None = None) -> DataSettings:
        cfg = load_yaml("data.yaml")
        mode = cfg["point_in_time"].get("edgar_acceptance_mode")
        if mode != "raw_as_utc":
            raise ValueError(f"edgar_acceptance_mode doit valoir 'raw_as_utc' (reçu : {mode!r})")
        base = data_dir or Path(
            os.environ.get("AMUNDI_DATA_DIR", ROOT / cfg["storage"]["data_dir"])
        )
        return cls(data_dir=Path(base), config=cfg)
