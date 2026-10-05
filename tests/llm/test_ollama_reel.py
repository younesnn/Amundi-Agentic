"""Vérification réelle contre Ollama local uniquement (profil `dev`). Exclu par défaut :
`pytest -m llm tests/llm/test_ollama_reel.py`. Aucun appel Gemini ni Groq : le profil `dev` n'a
qu'un modèle, local, et aucune clé n'est nécessaire."""

import os
import urllib.request
from datetime import date

import pytest
from pydantic import BaseModel

from amundi_agentic.llm import LLMClient, ProviderError, load_config

pytestmark = pytest.mark.llm

BASE = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
T = date(2024, 2, 1)


def _ollama_joignable() -> bool:
    if not BASE.startswith(("http://localhost", "http://127.0.0.1")):
        return False  # uniquement un Ollama local
    try:
        urllib.request.urlopen(BASE, timeout=2)  # noqa: S310
        return True
    except OSError:
        return False


@pytest.fixture
def client(tmp_path):
    if not _ollama_joignable():
        pytest.skip("Ollama local injoignable")
    c = LLMClient(
        load_config(),
        profile="dev",
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        quota_journal=tmp_path / "quotas.json",
    )
    compte = {"n": 0}
    complet = c._transport.completion

    def compte_appels(**kw):
        compte["n"] += 1
        return complet(**kw)

    c._transport.completion = compte_appels
    c.compte = compte
    return c


class Capitale(BaseModel):
    pays: str
    capitale: str


def test_complete_ollama_reel(client):
    r = client.complete(
        [{"role": "user", "content": "Réponds par un seul mot : capitale de la France ?"}],
        date_donnees=T,
        max_tokens=40,
    )
    assert "paris" in r.text.lower()
    assert r.record.fournisseur == "ollama" and r.record.modele_servi
    assert r.record.tokens_entree > 0 and r.record.cout_eur == 0 and r.record.tier == "dev"


def test_sortie_structuree_ollama_reel_et_cache(client):
    msgs = [
        {"role": "system", "content": "Tu réponds en JSON."},
        {"role": "user", "content": "Capitale de l'Italie ? Champs : pays, capitale."},
    ]
    r = client.complete_structured(Capitale, msgs, date_donnees=T, max_tokens=80)
    assert r.parsed.capitale.lower().startswith("rom")
    avant = client.compte["n"]
    r2 = client.complete_structured(Capitale, msgs, date_donnees=T, max_tokens=80)
    assert r2.parsed == r.parsed and r2.record.cache_hit and client.compte["n"] == avant


def test_embed_ollama_reel(client):
    try:
        r = client.embed(["rendement excédentaire", "volatilité"], date_donnees=T)
    except ProviderError as exc:
        pytest.skip(f"modèle d'embedding Ollama absent (ollama pull nomic-embed-text) : {exc}")
    assert len(r.vectors) == 2 and len(r.vectors[0]) > 10
    assert client.embed(["rendement excédentaire", "volatilité"], date_donnees=T).record.cache_hit
