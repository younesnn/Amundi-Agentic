"""Réglages communs de la suite : tests lents ignorés par défaut, délai sur les sous-processus.

- `@pytest.mark.slow` : tests de concurrence intensifs. Ignorés tant que `-m` ne cite pas `slow`
  (donc absents de la CI par défaut `-m "not llm and not network"`). En local :
  `uv run pytest -m slow` (ou `AMUNDI_RUN_SLOW=1 uv run pytest tests/llm`).
- Tout `subprocess.run` des tests reçoit un délai par défaut : un sous-processus figé fait
  échouer le test (`TimeoutExpired`) au lieu de bloquer la CI indéfiniment.
"""

import os
import subprocess

import pytest

DELAI_SOUS_PROCESSUS_S = 180


def pytest_collection_modifyitems(config, items):
    if "slow" in (config.getoption("markexpr") or "") or os.environ.get("AMUNDI_RUN_SLOW"):
        return
    ignore = pytest.mark.skip(reason="test lent : `uv run pytest -m slow` ou AMUNDI_RUN_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(ignore)


@pytest.fixture(autouse=True)
def _delai_par_defaut_des_sous_processus(monkeypatch):
    vrai = subprocess.run

    def avec_delai(*args, **kwargs):
        kwargs.setdefault("timeout", DELAI_SOUS_PROCESSUS_S)
        return vrai(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", avec_delai)
