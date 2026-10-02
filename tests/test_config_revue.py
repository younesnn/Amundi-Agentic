"""Tests complémentaires de config/llm.yaml (revue de D-008)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config" / "llm.yaml").read_text(encoding="utf-8"))

# Familles de modèles connues : aucun identifiant de ce type ne doit être codé en dur,
# y compris un modèle qui ne figure pas (ou plus) dans config/llm.yaml.
MOTIF_MODELE = re.compile(
    r"\b(gemini-[\w.\-]+|gpt-[\w.\-]+|gpt-oss[\w.\-]*|llama-?\d[\w.:\-]*|qwen\d?[\w.:\-]*"
    r"|claude-[\w.\-]+|mistral[\w.:\-]*|o[134]-(?:mini|preview)\b)",
    re.IGNORECASE,
)


def test_aucun_identifiant_de_modele_dans_le_code_ni_l_app():
    fichiers = list((ROOT / "src").rglob("*.py")) + list((ROOT / "app").rglob("*.py"))
    trouves = [
        f"{f.relative_to(ROOT)} : {m.group(0)}"
        for f in fichiers
        for m in MOTIF_MODELE.finditer(f.read_text(encoding="utf-8"))
    ]
    assert not trouves, "\n".join(trouves)


def test_variables_d_environnement_et_non_valeurs():
    """La config ne nomme que des variables d'environnement, jamais une valeur de clé."""
    for fournisseur, parametres in CONFIG["providers"].items():
        for cle, valeur in parametres.items():
            assert cle.endswith("_env"), f"{fournisseur}.{cle} : seules des références *_env"
            assert re.fullmatch(r"[A-Z][A-Z0-9_]*", valeur), f"{fournisseur}.{cle} = {valeur!r}"
            assert not valeur.startswith("ANTHROPIC"), "fournisseur payant interdit (D-004)"


def test_variables_de_la_config_declarees_dans_env_example():
    exemple = (ROOT / ".env.example").read_text(encoding="utf-8")
    declarees = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", exemple, flags=re.MULTILINE))
    attendues = {v for p in CONFIG["providers"].values() for v in p.values()}
    assert attendues <= declarees, attendues - declarees


def test_chaque_chaine_de_relais_commence_par_son_niveau_et_finit_hors_gemini():
    for niveau, chaine in CONFIG["fallback_order"].items():
        assert chaine[0] == niveau
        assert len(chaine) == len(set(chaine)), f"doublon dans la chaîne {niveau}"
        dernier = CONFIG["models"][chaine[-1]].split("/", 1)[0]
        assert dernier != "gemini", f"{niveau} : pas de relais hors du quota Gemini"


def test_mode_par_defaut_ne_consomme_aucun_quota():
    assert CONFIG["default_mode"] == "dev"
    assert CONFIG["models"]["dev"].startswith("ollama/")
