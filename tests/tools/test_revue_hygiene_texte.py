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


# --------------------------------------------------------------------------- gros fichiers
SEUIL_OCTETS = 300_000
EXTENSIONS_INTERDITES = {".gz", ".parquet", ".npz", ".pdf", ".zip"}
# Chemins gérés par des outils (hooks graphify, `uv lock`, rapport de couverture) : jamais jugés.
CHEMINS_GERES = ("graphify-out/", "uv.lock", "docs/couverture_donnees.md", "runs/data_coverage/")


def _git(*args: str) -> str | None:
    """Sortie de `git <args>` ou None (git absent, pas un dépôt, référence inconnue)."""
    try:
        r = subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return r.stdout if r.returncode == 0 else None


def _reference() -> str | None:
    """Référence de comparaison, indépendante de l'état de l'arbre de travail : le merge-base avec
    `origin/main` ; si on est déjà sur ce point (main fusionnée) ou si `origin/main` manque, le
    commit précédent `HEAD~1`. None si aucune des deux n'existe (clone superficiel d'un commit)."""
    tete = (_git("rev-parse", "HEAD") or "").strip()
    base = (_git("merge-base", "HEAD", "origin/main") or "").strip()
    if base and base != tete:
        return base
    parent = (_git("rev-parse", "--verify", "-q", "HEAD~1") or "").strip()
    return parent or None


def _gere(chemin: str) -> bool:
    return (
        chemin.startswith(CHEMINS_GERES[0])
        or chemin in CHEMINS_GERES
        or any(chemin.startswith(c) for c in CHEMINS_GERES if c.endswith("/"))
    )


def _fichiers_ajoutes() -> tuple[dict[str, int], str]:
    """{chemin: taille en octets} des fichiers AJOUTÉS depuis la référence (committés ou non) et des
    fichiers non suivis non ignorés ; + la description de la référence. Tailles lues dans Git
    (`cat-file -s`) pour les fichiers committés, sur disque pour les non suivis."""
    ref = _reference()
    ajoutes: dict[str, int] = {}
    if ref:
        noms = (_git("diff", "--name-only", "--diff-filter=A", ref, "HEAD") or "").splitlines()
        for nom in noms:
            taille = (_git("cat-file", "-s", f"HEAD:{nom}") or "").strip()
            if taille.isdigit():
                ajoutes[nom] = int(taille)
    for nom in (_git("diff", "--cached", "--name-only", "--diff-filter=A") or "").splitlines():
        f = RACINE / nom
        if f.is_file():
            ajoutes[nom] = f.stat().st_size
    for nom in (_git("ls-files", "--others", "--exclude-standard") or "").splitlines():
        f = RACINE / nom
        if f.is_file():
            ajoutes[nom] = f.stat().st_size
    return {k: v for k, v in sorted(ajoutes.items()) if not _gere(k)}, ref or "aucune"


def test_aucun_gros_fichier_dans_les_ajouts():
    """Empêche l'ajout de gros fichiers de données. Déterministe : compare à la référence Git
    (merge-base avec origin/main, ou HEAD~1), pas à l'état de l'arbre de travail ; les modifications
    de fichiers déjà suivis (graphify-out/...) ne comptent pas."""
    if _git("rev-parse", "--git-dir") is None:
        pytest.skip("pas de dépôt Git : contrôle des gros fichiers impossible")
    ajoutes, ref = _fichiers_ajoutes()
    if ref == "aucune" and not ajoutes:
        pytest.skip("aucune référence Git (clone d'un seul commit) et aucun fichier non suivi")
    for nom, taille in ajoutes.items():
        assert taille < SEUIL_OCTETS, f"{nom} : {taille} octets (>= {SEUIL_OCTETS}), base {ref}"
        assert Path(nom).suffix not in EXTENSIONS_INTERDITES, f"{nom} : extension interdite"


def test_chemins_geres_par_des_outils_jamais_juges():
    for chemin in (
        "graphify-out/graph.json",
        "graphify-out/x/y.json",
        "uv.lock",
        "docs/couverture_donnees.md",
        "runs/data_coverage/a.json",
    ):
        assert _gere(chemin), chemin
    for chemin in ("src/graphify-out/x", "data/gros.parquet", "docs/autre.md", "uv.lock.bak"):
        assert not _gere(chemin), chemin


def test_detection_d_un_gros_fichier_non_suivi_et_d_une_extension_interdite(tmp_path):
    """Le contrôle détecte bien : dépôt Git jetable avec un commit puis un fichier de 400 000 octets
    non suivi et un .parquet ; modifier un fichier suivi énorme ne déclenche rien."""

    def git(*a):
        subprocess.run(
            ["git", *a],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
                "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                "HOME": str(tmp_path),
            },
        )

    git("init", "-q")
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}")
    (tmp_path / "a.txt").write_text("a")
    git("add", "-A")
    git("commit", "-qm", "un")
    (tmp_path / "b.txt").write_text("b")
    git("add", "-A")
    git("commit", "-qm", "deux")
    (tmp_path / "graphify-out" / "graph.json").write_text(
        "x" * 2_000_000
    )  # modifié, suivi : ignoré
    (tmp_path / "gros.dat").write_bytes(b"x" * 400_000)
    (tmp_path / "petit.parquet").write_bytes(b"x")
    global RACINE
    ancien = RACINE
    RACINE = tmp_path
    try:
        ajoutes, ref = _fichiers_ajoutes()
    finally:
        RACINE = ancien
    assert ref != "aucune"
    assert "graphify-out/graph.json" not in ajoutes
    assert ajoutes["gros.dat"] == 400_000 and ajoutes["b.txt"] == 1  # b.txt ajouté depuis HEAD~1
    assert "a.txt" not in ajoutes
    assert (
        ajoutes["gros.dat"] >= SEUIL_OCTETS
        and Path("petit.parquet").suffix in EXTENSIONS_INTERDITES
    )
