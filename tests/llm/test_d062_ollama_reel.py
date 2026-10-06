"""D-062 : sonde réelle, Ollama local uniquement (aucun appel Gemini ni Groq). Reproduit la sonde
du lead : prompt d'environ 9 000 jetons, consigne au début et question à la fin.

`uv run pytest -m llm tests/llm/test_d062_ollama_reel.py` ; ne pas lancer en parallèle d'un autre
test Ollama. Le premier chargement du modèle avec un contexte de 16 384 jetons peut durer plus de
2 minutes : délai explicite de 600 s par appel."""

import os
import urllib.request
from datetime import date

import pytest

from amundi_agentic.llm import LLMClient, load_config

pytestmark = pytest.mark.llm

BASE = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
DELAI_S = 600


def _joignable() -> bool:
    if not BASE.startswith(("http://localhost", "http://127.0.0.1")):
        return False  # uniquement un Ollama local
    try:
        urllib.request.urlopen(BASE, timeout=2)  # noqa: S310
        return True
    except OSError:
        return False


def test_prompt_long_non_tronque_et_consigne_suivie(tmp_path):
    if not _joignable():
        pytest.skip("Ollama local injoignable")
    cfg = load_config(overrides={"defaults": {"timeout_s": DELAI_S}})
    c = LLMClient(
        cfg,
        profile="dev",
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        quota_journal=tmp_path / "quotas.json",
    )
    corps = "\n".join(
        f"Note {i} : le comité a examiné la ligne {i} du portefeuille sans conclure."
        for i in range(480)
    )
    prompt = (
        "Information importante : le mot secret de ce document est ZEBRE. Retiens-le.\n"
        + corps
        + "\nQuestion : quel est le mot secret annoncé au début du document ? "
        "Réponds uniquement par ce mot."
    )
    r = c.complete(
        [{"role": "user", "content": prompt}], date_donnees=date(2024, 2, 1), max_tokens=10
    )
    assert r.record.num_ctx == cfg.ollama.num_ctx
    assert r.record.prompt_tokens_evalues is not None and r.record.prompt_tokens_evalues > 8000
    assert "zebre" in r.text.lower().replace("è", "e").replace("é", "e")
