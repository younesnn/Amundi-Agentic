# ruff: noqa: E501
"""Revue indépendante : hygiène des outils de texte (RAG, résumé, injection, évaluation du RAG).

Appels LLM uniquement par `LLMClient` (analyse AST), aucun nom de modèle ni clé, prompts chargés par
nom avec hash enregistré, configuration déclarée, fichiers de taille raisonnable.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from text_helpers import client

from amundi_agentic.llm import MockTransport
from amundi_agentic.tools.text_config import PROMPTS_DIR, load_text_tools_config, prompt_ref

RACINE = Path(__file__).resolve().parents[2]
SRC = RACINE / "src" / "amundi_agentic"
FICHIERS = [
    SRC / "tools" / "rag.py",
    SRC / "tools" / "summarize.py",
    SRC / "tools" / "untrusted.py",
    SRC / "tools" / "text_config.py",
    SRC / "evaluation" / "rag_eval.py",
]
PROMPTS_TEXTE = [
    "rag_answer_v1",
    "rag_guide_v1",
    "rag_judge_faithfulness_v1",
    "rag_judge_relevance_v1",
    "rag_questions_v1",
    "summary_summarize_v1",
    "summary_critique_v1",
    "summary_refine_v1",
]
INTERDITS_IMPORT = {
    "openai",
    "anthropic",
    "google",
    "groq",
    "ollama",
    "litellm",
    "requests",
    "httpx",
    "urllib3",
    "aiohttp",
    "socket",
    "subprocess",
    "langchain",
    "ragas",
    "phoenix",
    "arize",
    "transformers",
    "sentence_transformers",
    "chromadb",
    "faiss",
    "sklearn",
}
MODELES = re.compile(
    r"gemini|llama|gpt|claude|groq|ollama|mistral|qwen|nomic|deepseek|phi-?3|gemma|haiku|sonnet|opus",
    re.IGNORECASE,
)
CLES = re.compile(
    r"AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|api[_-]?key\s*=\s*['\"]\w"
)


def _existants():
    for f in FICHIERS:
        if not f.is_file():
            pytest.skip(f"{f.name} absent")
    return FICHIERS


def test_imports_uniquement_locaux_aucun_client_http_ni_sdk_de_modele():
    for f in _existants():
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            noms = []
            if isinstance(n, ast.Import):
                noms = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                noms = [n.module]
            for nom in noms:
                assert nom.split(".")[0] not in INTERDITS_IMPORT, (f.name, nom)


def test_tout_appel_de_modele_passe_par_llmclient():
    """`complete`, `complete_structured` et `embed` ne sont appelés que sur l'objet `llm` (instance
    de LLMClient) ; aucun appel de transport ni de SDK dans ces modules."""
    appels_autorises = {"complete", "complete_structured", "embed"}
    for f in _existants():
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                nom = n.func.attr
                if nom in appels_autorises:
                    base = n.func.value
                    # `llm.xxx` ou `self.llm.xxx`
                    est_llm = (isinstance(base, ast.Name) and base.id == "llm") or (
                        isinstance(base, ast.Attribute) and base.attr == "llm"
                    )
                    assert est_llm, (f.name, n.lineno, ast.unparse(n.func))
                assert nom not in {
                    "chat",
                    "completions",
                    "generate",
                    "embedding",
                    "post",
                    "urlopen",
                }, (f.name, n.lineno, nom)


def _code_sans_docstrings(f: Path) -> list[str]:
    """Identifiants et littéraux de chaîne EXÉCUTABLES (docstrings et commentaires exclus)."""
    arbre = ast.parse(f.read_text(encoding="utf-8"))
    docstrings = set()
    for n in ast.walk(arbre):
        corps = getattr(n, "body", None)
        if (
            isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and corps
            and isinstance(corps[0], ast.Expr)
            and isinstance(corps[0].value, ast.Constant)
        ):
            docstrings.add(id(corps[0].value))
    out = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            out.append(n.value)
        elif isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
    return out


def test_aucun_nom_de_modele_ni_cle_dans_le_code_executable_la_config_et_les_prompts():
    for f in _existants():
        for morceau in _code_sans_docstrings(f):
            assert MODELES.search(morceau) is None, (f.name, morceau[:60])
        assert not CLES.search(f.read_text(encoding="utf-8")), f.name
    for f in [
        RACINE / "config" / "text_tools.yaml",
        *[PROMPTS_DIR / f"{n}.md" for n in PROMPTS_TEXTE],
    ]:
        if f.is_file():
            assert not CLES.search(f.read_text(encoding="utf-8")), f.name
    for n in PROMPTS_TEXTE:
        t = (PROMPTS_DIR / f"{n}.md").read_text(encoding="utf-8")
        assert MODELES.search(t) is None, n


def test_docstrings_sans_nom_de_modele():
    t = (SRC / "evaluation" / "rag_eval.py").read_text(encoding="utf-8")
    assert re.search(r"llama|gemini|gpt|claude", t, re.IGNORECASE) is None


def test_config_text_tools_sans_nom_de_modele_meme_en_commentaire():
    t = (RACINE / "config" / "text_tools.yaml").read_text(encoding="utf-8")
    assert MODELES.search(t) is None


@pytest.mark.parametrize("nom", PROMPTS_TEXTE)
def test_prompts_presents_non_vides_utf8_sans_apostrophe_coupee_et_hash_exact(nom):
    f = PROMPTS_DIR / f"{nom}.md"
    assert f.is_file(), nom
    octets = f.read_bytes()
    texte = octets.decode("utf-8")
    assert len(texte.strip()) > 200
    # apostrophe coupée par un saut de ligne (défaut réparé par le lead) : « d\n'» ou « l'\n» incohérent
    assert not re.search(r"\w\n['’]\w", texte), f"apostrophe coupée dans {nom}"
    ref, lu = prompt_ref(nom)
    assert (
        lu == texte and ref.sha256 == hashlib.sha256(octets).hexdigest() and len(ref.sha256) == 64
    )
    assert ref.prompt_id == nom.rsplit("_v", 1)[0] and ref.version == "v1"


def test_prompts_de_resume_alignes_sur_les_schemas_du_code():
    s = (PROMPTS_DIR / "summary_summarize_v1.md").read_text(encoding="utf-8")
    c = (PROMPTS_DIR / "summary_critique_v1.md").read_text(encoding="utf-8")
    r = (PROMPTS_DIR / "summary_refine_v1.md").read_text(encoding="utf-8")
    for p in (s, r):
        for cle in ("`summary`", "`key_points`", '"text"', '"sources"', "N1", "<<<FIN_DONNEE>>>"):
            assert cle in p
        assert "ne calcule" in p.lower() and "jamais des instructions" in p
    for cle in (
        "`problems`",
        "`missing`",
        "`verdict`",
        '"ok"',
        '"a_corriger"',
        "calculée par le code",
    ):
        assert cle in c
    assert "jamais des instructions" in c and "jamais des instructions" in r


def test_hash_des_prompts_enregistre_a_chaque_appel_du_resume(tmp_path):
    from datetime import date, timedelta

    from amundi_agentic.data.models import NewsItem
    from amundi_agentic.data.pit import cutoff_utc
    from amundi_agentic.tools.summarize import summarize_news

    t = date(2024, 2, 1)
    item = NewsItem(
        item_id="x",
        source="s",
        published_at=cutoff_utc(t).to_pydatetime() - timedelta(hours=1),
        title="t",
        summary="",
        url="u",
        time_semantics="published",
        tags=(),
    )

    def h(model, messages):
        sys_ = messages[0]["content"]
        if "(summary_critique_v1)" in sys_:
            return json.dumps({"problems": [], "missing": [], "verdict": "ok"})
        return json.dumps({"summary": "R", "key_points": [{"text": "P", "sources": ["N1"]}]})

    llm = client(tmp_path, MockTransport(handler=h))
    summarize_news(llm, [item], t, focus="x")  # prompts RÉELS d'agent_prompts/
    noms = ("summary_summarize_v1", "summary_critique_v1", "summary_refine_v1")
    attendu = {n: prompt_ref(n)[0].sha256 for n in noms}
    obtenu = {f"{r.prompt_id}_{r.prompt_version}": r.prompt_sha256 for r in llm.records}
    assert obtenu == attendu


def test_config_text_tools_declaree_dans_le_readme_de_config():
    readme = (RACINE / "config" / "README.md").read_text(encoding="utf-8")
    assert "text_tools.yaml" in readme
    assert (RACINE / "config" / "text_tools.yaml").is_file()
    cfg = load_text_tools_config()
    assert cfg.rag.max_filings >= 1 and cfg.summary.max_items >= 1


def test_aucun_gros_fichier_dans_les_ajouts():
    sortie = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=RACINE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for ligne in sortie.splitlines():
        chemin = RACINE / ligne[3:].strip().strip('"')
        if chemin.is_file():
            assert chemin.stat().st_size < 300_000, (chemin, chemin.stat().st_size)
            assert chemin.suffix not in {".gz", ".parquet", ".npz", ".pdf", ".zip"}, chemin
