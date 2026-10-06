"""Vérification réelle contre Ollama local UNIQUEMENT (profil `dev`), exclue par défaut :
`uv run pytest -m llm tests/agents/test_ollama_reel.py`. Aucun appel Gemini ni Groq, aucune clé.

Un petit modèle local peut produire des vues rejetées par le contrôle d'ancrage : c'est le
comportement attendu (rejet motivé, journalisé), pas un échec ; le test vérifie la mécanique, pas
la qualité des vues.
"""

from __future__ import annotations

import os
import urllib.request
from datetime import date

import pytest
from agents_helpers import fabrique_ctx

from amundi_agentic.agents.valuation import ValuationAgent
from amundi_agentic.llm import LLMClient, load_config

pytestmark = pytest.mark.llm

BASE = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")


def _joignable() -> bool:
    if not BASE.startswith(("http://localhost", "http://127.0.0.1")):
        return False
    try:
        urllib.request.urlopen(BASE, timeout=2)  # noqa: S310
        return True
    except OSError:
        return False


def test_valuation_avec_llama_local(tmp_path):
    if not _joignable():
        pytest.skip("Ollama local injoignable")
    ctx = fabrique_ctx(tmp_path)
    ctx.llm = LLMClient(
        load_config(),
        mode="interactif",
        profile="dev",
        run_id="test",
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        quota_journal=tmp_path / "quotas.json",
    )
    r = ValuationAgent("allocation").analyse(ctx, ["actions_etats_unis"])
    assert (
        r.turn.appels_outils
    )  # les outils tournent toujours, quelle que soit la réponse du modèle
    assert r.turn.vues or r.rejets  # vue valide ou rejet motivé, jamais un silence
    assert all(a.record.fournisseur == "ollama" for a in ctx.appels)
    for v in r.turn.vues:
        assert {s.source_id for s in v.sources} <= {
            a.resultat["meta"]["source_id"] for a in r.turn.appels_outils
        }
    assert date(2024, 2, 1) == ctx.t
