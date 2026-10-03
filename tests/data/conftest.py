"""Fabriques de données synthétiques pour les tests de la couche `data/` (aucun réseau, aucune clé)."""

from __future__ import annotations

import pytest

from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore


@pytest.fixture
def cfg() -> dict:
    return load_yaml("data.yaml")


@pytest.fixture
def store(tmp_path) -> ParquetStore:
    return ParquetStore(tmp_path / "store")


@pytest.fixture
def pit(store, cfg) -> PointInTimeStore:
    return PointInTimeStore(store, cfg)
