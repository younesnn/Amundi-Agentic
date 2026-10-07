"""Tests du socle (phase 0) : structure du dépôt et hygiène des secrets."""

import importlib
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SOUS_PAQUETS = [
    "llm",
    "data",
    "tools",
    "agents",
    "debate",
    "portfolio",
    "rebalancing",
    "explain",
    "evaluation",
]


def test_paquet_importable_avec_avertissement():
    paquet = importlib.import_module("amundi_agentic")
    assert "pas un conseil en investissement" in paquet.DISCLAIMER


@pytest.mark.parametrize("nom", SOUS_PAQUETS)
def test_sous_paquets_de_la_section_5_2(nom):
    importlib.import_module(f"amundi_agentic.{nom}")


@pytest.mark.parametrize(
    "chemin",
    [
        "PROMPT.md",
        "PROGRESS.md",
        "DECISIONS.md",
        "HYPOTHESES.md",
        "README.md",
        "docs/tracabilite.md",
        ".env.example",
    ],
)
def test_fichiers_de_pilotage_presents(chemin):
    assert (ROOT / chemin).is_file()


def test_env_ignore_par_git():
    resultat = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT, check=False)
    assert resultat.returncode == 0, ".env doit être ignoré par Git"


def test_env_example_sans_secret_ni_cle_anthropic():
    for ligne in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, _, valeur = ligne.partition("=")
        assert cle != "ANTHROPIC_API_KEY"
        if re.search(r"(KEY|TOKEN|SECRET)$", cle):
            assert valeur == "", f"{cle} doit rester vide dans .env.example"


def test_readme_porte_l_avertissement():
    assert "pas un conseil en investissement" in (ROOT / "README.md").read_text(encoding="utf-8")
