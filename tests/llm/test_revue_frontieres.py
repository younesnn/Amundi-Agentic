"""Revue indépendante : frontières d'import, imports dynamiques, noms de modèles dans tout src/."""

import ast
import re
import textwrap
from pathlib import Path

import pytest

from amundi_agentic.llm import load_config

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "amundi_agentic"
SDK = ("litellm", "openai", "anthropic", "google", "groq", "ollama", "langchain", "langgraph")
PROJET = "amundi_agentic"


def _modules_importes(arbre: ast.AST, paquet: str) -> set[str]:
    """Modules importés statiquement ou dynamiquement (importlib, __import__), imports relatifs
    résolus par rapport à `paquet` (ex. 'amundi_agentic.llm')."""
    noms: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = paquet.split(".")
                base = base[: len(base) - (n.level - 1)]
                noms.add(".".join([*base, *([n.module] if n.module else [])]))
                noms.update(
                    ".".join([*base, *([n.module] if n.module else []), a.name]) for a in n.names
                )
            elif n.module:
                noms.add(n.module)
                noms.update(f"{n.module}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Call):
            f = n.func
            nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nom in ("import_module", "__import__", "find_spec") and n.args:
                a0 = n.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    noms.add(a0.value)
                else:
                    noms.add("<dynamique-non-resolu>")
    return noms


def _fichiers():
    return sorted(p for p in SRC.rglob("*.py"))


def _paquet(f: Path) -> str:
    rel = f.relative_to(SRC.parent).with_suffix("")
    return ".".join(rel.parts[:-1])


def _est_sdk(m: str) -> bool:
    return any(m == s or m.startswith(s + ".") for s in SDK)


def test_sdk_et_litellm_uniquement_dans_transport_y_compris_imports_dynamiques():
    fautes = []
    for f in _fichiers() + list((ROOT / "app").rglob("*.py")):
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        mods = _modules_importes(arbre, _paquet(f) if f.is_relative_to(SRC) else "app")
        if "<dynamique-non-resolu>" in mods:
            fautes.append(f"{f.relative_to(ROOT)} : import dynamique non résolu")
        sdk = {m for m in mods if _est_sdk(m)}
        if sdk and f != SRC / "llm" / "transport.py":
            fautes.append(f"{f.relative_to(ROOT)} importe {sorted(sdk)}")
    assert not fautes, "\n".join(fautes)


def test_transport_est_le_seul_a_nommer_litellm_meme_en_chaine():
    for f in _fichiers():
        if f == SRC / "llm" / "transport.py":
            continue
        t = f.read_text(encoding="utf-8")
        # Aucun appel qui construit dynamiquement le nom d'un module à importer.
        assert not re.search(r"importlib|__import__", t) or f.name == "manifest.py", f.name


def test_detecteur_d_imports_dynamiques_fonctionne():
    code = textwrap.dedent(
        """
        import importlib
        x = importlib.import_module("litellm")
        y = __import__("openai.types")
        z = importlib.import_module(nom)
        from . import a
        from ..data import b
        """
    )
    mods = _modules_importes(ast.parse(code), "amundi_agentic.llm")
    assert {"litellm", "openai.types", "<dynamique-non-resolu>"} <= mods
    assert "amundi_agentic.data" in mods and "amundi_agentic.llm.a" in mods


def test_schemas_n_importe_rien_du_projet():
    mods = _modules_importes(
        ast.parse((SRC / "schemas.py").read_text(encoding="utf-8")), "amundi_agentic"
    )
    assert not [m for m in mods if m == PROJET or m.startswith(PROJET + ".")]


@pytest.mark.parametrize(
    "interdit", ["data", "tools", "agents", "debate", "portfolio", "evaluation"]
)
def test_llm_n_importe_ni_data_ni_tools_ni_agents(interdit):
    fautes = []
    for f in (SRC / "llm").rglob("*.py"):
        mods = _modules_importes(ast.parse(f.read_text(encoding="utf-8")), _paquet(f))
        fautes += [
            f"{f.name}: {m}"
            for m in mods
            if m == f"{PROJET}.{interdit}" or m.startswith(f"{PROJET}.{interdit}.")
        ]
    assert not fautes


def test_llm_ne_depend_que_de_schemas_et_de_lui_meme():
    for f in (SRC / "llm").rglob("*.py"):
        mods = _modules_importes(ast.parse(f.read_text(encoding="utf-8")), _paquet(f))
        internes = {m for m in mods if m.startswith(PROJET + ".")}
        assert all(m.startswith((f"{PROJET}.llm", f"{PROJET}.schemas")) for m in internes), (
            f.name,
            internes,
        )


def test_aucun_nom_de_modele_dans_tout_src():
    cfg = load_config()
    ident = [*cfg.models.values(), *cfg.evaluation.models.values(), *cfg.embeddings.values()]
    noms = {i.split("/", 1)[1] for i in ident}
    motif = re.compile(
        r"\b(gemini-[\w.\-]+|gpt-oss[\w.\-]*|llama-?\d[\w.:\-]*|nomic-embed[\w\-]*)", re.I
    )
    fautes = []
    for f in _fichiers():
        t = f.read_text(encoding="utf-8")
        fautes += [f"{f.relative_to(ROOT)}: {n}" for n in noms if n in t]
        fautes += [f"{f.relative_to(ROOT)}: {m.group(0)}" for m in motif.finditer(t)]
    assert not fautes, "\n".join(fautes)


def test_aucun_appel_http_direct_vers_un_fournisseur_dans_src():
    motif = re.compile(
        r"generativelanguage\.googleapis|api\.groq\.com|localhost:11434|api\.openai\.com"
    )
    fautes = [f.name for f in _fichiers() if motif.search(f.read_text(encoding="utf-8"))]
    assert not fautes, fautes


def test_aucune_variable_anthropic_ni_cle_lue_hors_de_transport():
    for f in _fichiers():
        t = f.read_text(encoding="utf-8")
        assert ("ANTHROPIC" + "_API_KEY") not in t, f.name
        if f.name != "transport.py" and f.parent.name != "llm":
            assert not re.search(r"environ(\.get|\[)\(?[\"'][A-Z_]*_API_KEY", t), f.name
