"""Outils du cache LLM : `uv run python -m amundi_agentic.llm purge-cache <fournisseur|--all>`.

Sert à purger les réponses d'un fournisseur (par exemple `ollama`, après un changement de
contexte ou de modèle). Aucune clé n'est lue ni affichée. Seules les entrées de cache valides
(`<sha256>.json` dans un sous-dossier hexadécimal de deux caractères) sont supprimées ; les liens
symboliques ne sont jamais suivis ; un dossier qui n'est pas un cache LLM est refusé (code 3).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from amundi_agentic.llm.cache import DiskCache
from amundi_agentic.llm.config import load_config, resolve_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m amundi_agentic.llm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("purge-cache", help="supprime les entrées de cache d'un fournisseur")
    p.add_argument("provider", nargs="?", help="gemini, groq, ollama...")
    p.add_argument("--all", action="store_true", help="purge tous les fournisseurs")
    p.add_argument("--dir", type=Path, default=None, help="dossier de cache (défaut : config)")
    args = ap.parse_args(argv)
    if not args.provider and not args.all:
        ap.error("indiquer un fournisseur ou --all")
    dossier = args.dir or resolve_path(load_config().cache.dir)
    cache = DiskCache(dossier)
    refus = cache.refus_purge()
    if refus:
        print(f"purge refusée : {refus}", file=sys.stderr)
        return 3
    cible = None if args.all else args.provider
    if args.all:
        print(f"--all : purge de TOUS les fournisseurs dans {dossier}")
    detail = cache.purge_detail(cible)
    n = sum(detail.values())
    print(f"{n} entrée(s) supprimée(s) dans {dossier}")
    for fournisseur, k in sorted(detail.items()):
        print(f"  {fournisseur} : {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
