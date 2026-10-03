"""Rend `tools_helpers` importable (le mode `importlib` n'ajoute pas le dossier au chemin)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
