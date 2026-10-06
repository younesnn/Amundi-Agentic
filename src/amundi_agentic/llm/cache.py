"""Cache disque des réponses (EX-NF-04) : une requête identique ne part jamais deux fois.

Clé = SHA-256 de (type d'appel, modèle demandé, messages, schéma, paramètres, `date_donnees`).
Aucune clé d'API n'entre dans la clé ni dans les fichiers. Écriture atomique : un fichier est
complet ou absent, ce qui permet la reprise après interruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

_SOUS_DOSSIER = re.compile(r"[0-9a-f]{2}")
_NOM_ENTREE = re.compile(r"[0-9a-f]{64}\.json")
_FICHIERS_RACINE = {"quotas.json", "quotas.json.lock"}  # journal des quotas (même dossier)
_TAILLE_MAX = 64 * 1024 * 1024


def _est_dossier_reel(e: os.DirEntry[str]) -> bool:
    return e.is_dir(follow_symlinks=False) and not e.is_symlink()


# Version du schéma de clé. 2 (D-062) : invalide les caches produits avant la prise en compte de
# `num_ctx` (réponses obtenues avec un prompt tronqué en silence par Ollama).
CACHE_KEY_VERSION = 2


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
        "v": CACHE_KEY_VERSION,
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

    def _entrees_valides(self) -> list[tuple[Path, str]]:
        """Fichiers réguliers de cache reconnus (chemin, fournisseur) : sous-dossier de deux
        caractères hexadécimaux, nom `<sha256>.json` préfixé par ce sous-dossier, dict avec les
        champs d'une entrée (`modele_servi`, et `text` ou `vectors`). Ne suit jamais un lien
        symbolique (fichier ou dossier) ; ignore tout le reste sans le toucher."""
        trouvees: list[tuple[Path, str]] = []
        racine = self.directory
        if racine.is_symlink() or not racine.is_dir():
            return trouvees
        with os.scandir(racine) as it:
            sous_dossiers = [
                e for e in it if _SOUS_DOSSIER.fullmatch(e.name) and _est_dossier_reel(e)
            ]
        for sd in sous_dossiers:
            with os.scandir(sd.path) as it:
                for e in it:
                    if not _NOM_ENTREE.fullmatch(e.name) or e.name[:2] != sd.name:
                        continue
                    if e.is_symlink() or not e.is_file(follow_symlinks=False):
                        continue
                    try:
                        if e.stat(follow_symlinks=False).st_size > _TAILLE_MAX:
                            continue
                        with open(e.path, encoding="utf-8") as f:
                            entree = json.load(f)
                    except (ValueError, OSError):
                        continue
                    if (
                        isinstance(entree, dict)
                        and "modele_servi" in entree
                        and ("text" in entree or "vectors" in entree)
                        and isinstance(entree.get("fournisseur"), str)
                    ):
                        trouvees.append((Path(e.path), entree["fournisseur"]))
        return trouvees

    def refus_purge(self) -> str | None:
        """Motif de refus si le dossier n'est pas un dossier de cache LLM reconnaissable
        (`/`, répertoire personnel, dépôt, ancêtre de ceux-ci, sous-dossier étranger,
        fichier étranger à la racine) ; None sinon. Un dossier absent n'a rien à purger."""
        if self.directory.is_symlink():
            return "le dossier de cache est un lien symbolique"
        if not self.directory.is_dir():
            return None
        reel = self.directory.resolve()
        depot = Path(__file__).resolve().parents[3]
        maison = Path.home().resolve()
        if (
            reel in {Path(reel.anchor), maison, depot}
            or reel in maison.parents
            or (reel in depot.parents)
        ):
            return f"{reel} n'est pas un dossier de cache (racine, répertoire personnel ou dépôt)"
        with os.scandir(reel) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    if not _SOUS_DOSSIER.fullmatch(e.name):
                        return f"sous-dossier étranger {e.name!r} : ce n'est pas un cache LLM"
                elif e.is_symlink():
                    continue  # jamais suivi, jamais supprimé
                elif e.name not in _FICHIERS_RACINE and not e.name.startswith("."):
                    return f"fichier étranger {e.name!r} à la racine : ce n'est pas un cache LLM"
        return None

    def purge_detail(self, provider: str | None = None) -> dict[str, int]:
        """Supprime les seules entrées de cache valides du fournisseur (toutes si `provider` est
        None) et renvoie le nombre de fichiers supprimés par fournisseur. Ne supprime jamais un
        dossier, un lien symbolique ni un fichier qui n'est pas une entrée de cache."""
        compte: dict[str, int] = {}
        for chemin, fournisseur in self._entrees_valides():
            if provider is not None and fournisseur != provider:
                continue
            if chemin.is_symlink():
                continue
            try:
                chemin.unlink()
            except OSError:
                continue
            compte[fournisseur] = compte.get(fournisseur, 0) + 1
        return compte

    def purge(self, provider: str | None = None) -> int:
        """Nombre de fichiers supprimés (voir `purge_detail`)."""
        return sum(self.purge_detail(provider).values())

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
