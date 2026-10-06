"""Rend `agents_helpers` importable (le mode `importlib` n'ajoute pas le dossier au chemin)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1] / "debate"))

from agents_helpers import fabrique_ctx  # noqa: E402


@pytest.fixture
def ctx(tmp_path):
    return fabrique_ctx(tmp_path)
