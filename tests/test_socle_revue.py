"""Tests complémentaires du socle (revue phase 0) : CI, version de Python, secrets."""

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

# Formats publics des clés des fournisseurs (Google/Gemini, Groq, OpenAI, Anthropic).
MOTIFS_CLES = re.compile(
    r"AIza[0-9A-Za-z_\-]{30,}|gsk_[0-9A-Za-z]{30,}|sk-ant-[0-9A-Za-z_\-]{20,}|sk-[0-9A-Za-z]{32,}"
)
# Variables non secrètes autorisées à porter une valeur par défaut dans .env.example.
VALEURS_PAR_DEFAUT_AUTORISEES = {"OLLAMA_API_BASE"}


def _fichiers_commitables() -> list[Path]:
    """Fichiers suivis ou non ignorés : ce qui partirait dans un `git add -A`."""
    sortie = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return [ROOT / nom for nom in sortie.split("\0") if nom]


def test_python_version_respecte_requires_python():
    version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    majeur, mineur = (int(x) for x in version.split(".")[:2])
    minimum = re.fullmatch(r">=\s*(\d+)\.(\d+)", PYPROJECT["project"]["requires-python"])
    assert minimum, "requires-python doit rester de la forme >=X.Y"
    assert (majeur, mineur) >= (int(minimum.group(1)), int(minimum.group(2)))
    assert (majeur, mineur) >= (3, 11), "le prompt maître exige Python 3.11+"


def test_ci_lance_les_commandes_attendues():
    for commande in (
        "uv sync --locked",
        "uv run ruff check .",
        "uv run ruff format --check .",
        'uv run pytest -m "not llm and not network"',
    ):
        assert commande in CI, f"commande absente de la CI : {commande}"


def test_marqueurs_exclus_par_la_ci_sont_declares():
    declares = {
        m.split(":")[0].strip() for m in PYPROJECT["tool"]["pytest"]["ini_options"]["markers"]
    }
    expression = re.search(r'pytest -m "([^"]+)"', CI).group(1)
    exclus = set(re.findall(r"not (\w+)", expression))
    assert exclus == {"llm", "network"}
    assert exclus <= declares


def test_env_example_sans_aucune_valeur_hors_liste_blanche():
    """Aucune valeur pré-remplie, y compris hors suffixe KEY (ex. User-Agent avec e-mail)."""
    for ligne in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, _, valeur = ligne.partition("=")
        if cle not in VALEURS_PAR_DEFAUT_AUTORISEES:
            assert valeur == "", f"{cle} doit rester vide dans .env.example"


@pytest.mark.parametrize("nom", [".env", ".env.local", ".env.production"])
def test_variantes_env_ignorees(nom):
    resultat = subprocess.run(["git", "check-ignore", "-q", nom], cwd=ROOT, check=False)
    assert resultat.returncode == 0, f"{nom} doit être ignoré par Git"


def test_env_example_non_ignore():
    resultat = subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=ROOT, check=False)
    assert resultat.returncode == 1, ".env.example doit rester commitable"


def test_aucune_cle_d_api_dans_les_fichiers_commitables():
    fuites = []
    for chemin in _fichiers_commitables():
        if not chemin.is_file() or chemin.suffix.lower() == ".pdf":
            continue
        try:
            texte = chemin.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if MOTIFS_CLES.search(texte):
            fuites.append(str(chemin.relative_to(ROOT)))
    assert not fuites, f"motif de clé d'API trouvé dans : {fuites}"


def test_aucune_cle_anthropic_hors_interdictions():
    """ANTHROPIC_API_KEY ne doit apparaître que pour être interdite, jamais être lue."""
    autorises = {"CLAUDE.md", "DECISIONS.md", "tests/test_socle.py", "tests/test_socle_revue.py"}
    for chemin in _fichiers_commitables():
        rel = chemin.relative_to(ROOT).as_posix()
        if rel in autorises or rel.startswith(("prompts/", "fiches/", "graphify-out/")):
            continue
        if not chemin.is_file() or chemin.suffix.lower() == ".pdf":
            continue
        try:
            texte = chemin.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert "ANTHROPIC_API_KEY" not in texte, f"ANTHROPIC_API_KEY mentionnée dans {rel}"
