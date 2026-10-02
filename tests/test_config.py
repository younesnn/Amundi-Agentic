"""Configuration LLM : modèles déclarés dans config/, jamais codés en dur (C1, D-008)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config" / "llm.yaml").read_text(encoding="utf-8"))


def test_modeles_retenus_par_d_008():
    assert CONFIG["models"] == {
        "main": "gemini/gemini-flash-latest",
        "light": "gemini/gemini-flash-lite-latest",
        "fallback": "groq/openai/gpt-oss-120b",
        "dev": "ollama/llama3.1:8b",
    }


def test_ordre_de_relais_ne_cite_que_des_modeles_declares():
    for chaine in CONFIG["fallback_order"].values():
        assert set(chaine) <= set(CONFIG["models"])


def test_fournisseurs_gratuits_uniquement():
    fournisseurs = {nom.split("/", 1)[0] for nom in CONFIG["models"].values()}
    assert fournisseurs <= {"gemini", "groq", "ollama"}
    assert set(CONFIG["providers"]) == {"gemini", "groq", "ollama"}


def test_aucun_nom_de_modele_dans_le_code():
    noms = [nom.split("/", 1)[1] for nom in CONFIG["models"].values()]
    for fichier in (ROOT / "src").rglob("*.py"):
        texte = fichier.read_text(encoding="utf-8")
        for nom in noms:
            assert nom not in texte, f"{nom} codé en dur dans {fichier}"


def test_temperature_zero_par_defaut():
    assert CONFIG["defaults"]["temperature"] == 0
