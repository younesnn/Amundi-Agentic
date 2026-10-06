"""Rend les aides de tests importables (le mode `importlib` n'ajoute pas les dossiers au chemin)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "agents"))
sys.path.insert(0, str(Path(__file__).parent))
