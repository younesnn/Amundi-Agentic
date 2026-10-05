"""Garde-fous : aucun SDK de fournisseur hors de llm/, aucun nom de modèle dans le code, aucune
clé dans le code, le cache, les journaux ni les messages d'erreur (EX-NF-05, EX-NF-07, C1)."""

import ast
import json
import logging
import re
from datetime import date
from pathlib import Path

import pytest

from amundi_agentic.llm import MockLLMClient, ProviderError, load_config
from amundi_agentic.llm.redact import MASQUE, redact

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "amundi_agentic"
T = date(2024, 2, 1)
MSG = [{"role": "user", "content": "Bonjour"}]

SDK = ("litellm", "openai", "anthropic", "google.genai", "google.generativeai", "groq", "ollama")

# Clés factices construites à l'exécution : aucun motif de clé n'apparaît dans ce fichier.
CLE_GEMINI = "AIza" + "Sy" + "x" * 33
CLE_GROQ = "gsk_" + "y" * 40


def _imports(fichier: Path) -> set[str]:
    noms = set()
    for n in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            noms.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            noms.add(n.module)
    return noms


def _est_sdk(module: str) -> bool:
    if module.startswith("langchain_") and not module.startswith("langchain_core"):
        return True
    return any(module == s or module.startswith(s + ".") for s in SDK)


def test_aucune_importation_de_sdk_hors_de_llm():
    fautes = []
    for f in [*SRC.rglob("*.py"), *(ROOT / "app").rglob("*.py")]:
        if f.relative_to(ROOT).parts[:3] == ("src", "amundi_agentic", "llm"):
            continue
        fautes += [f"{f.relative_to(ROOT)} importe {m}" for m in _imports(f) if _est_sdk(m)]
    assert not fautes, "\n".join(fautes)


def test_litellm_n_est_importe_que_par_le_transport():
    """Le test précédent n'est pas vide : llm/transport.py est bien le seul importeur."""
    importeurs = {
        f.name for f in (SRC / "llm").rglob("*.py") if any(_est_sdk(m) for m in _imports(f))
    }
    assert importeurs == {"transport.py"}


def test_aucun_nom_de_modele_dans_le_code_de_llm():
    cfg = load_config()
    identifiants = [*cfg.models.values(), *cfg.evaluation.models.values(), *cfg.embeddings.values()]
    noms = {i.split("/", 1)[1] for i in identifiants}
    motif = re.compile(
        r"\b(gemini-[\w.\-]+|gpt-[\w.\-]+|gpt-oss[\w.\-]*|llama-?\d[\w.:\-]*|qwen\d?[\w.:\-]*"
        r"|claude-[\w.\-]+|mistral[\w.:\-]*)",
        re.IGNORECASE,
    )
    fautes = []
    for f in [*(SRC / "llm").rglob("*.py"), SRC / "schemas.py"]:
        texte = f.read_text(encoding="utf-8")
        fautes += [f"{f.name}: {n}" for n in noms if n in texte]
        fautes += [f"{f.name}: {m.group(0)}" for m in motif.finditer(texte)]
    assert not fautes, "\n".join(fautes)


def test_aucune_cle_codee_dans_le_code():
    motif = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|gsk_[0-9A-Za-z]{30,}|sk-[0-9A-Za-z]{32,}")
    for f in [*(SRC / "llm").rglob("*.py"), SRC / "schemas.py"]:
        assert not motif.search(f.read_text(encoding="utf-8")), f.name


def test_aucun_anthropic_dans_llm():
    for f in (SRC / "llm").rglob("*.py"):
        texte = f.read_text(encoding="utf-8").lower()
        assert "anthropic" not in texte, f.name


# --------------------------------------------------------------------------- masquage


@pytest.mark.parametrize(
    "texte",
    [
        f"erreur sur https://exemple.invalid/v1?key={CLE_GEMINI}&alt=json",
        f"Authorization: Bearer {CLE_GROQ}",
        f"api_key={CLE_GEMINI}",
        f'{{"api_key": "{CLE_GROQ}"}}',
        f"clé {CLE_GEMINI} refusée",
    ],
)
def test_redact_masque_les_cles(texte):
    sortie = redact(texte)
    assert CLE_GEMINI not in sortie and CLE_GROQ not in sortie
    assert MASQUE in sortie


def test_redact_masque_la_valeur_des_variables_d_environnement(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "valeur-secrete-12345")
    assert "valeur-secrete-12345" not in redact("échec avec valeur-secrete-12345 dedans")


def test_redact_laisse_passer_un_message_normal():
    assert redact("503 Service Unavailable") == "503 Service Unavailable"


# --------------------------------------------------------------------------- aucune clé en sortie


def _tout_le_texte(dossier: Path) -> str:
    return "\n".join(
        f.read_text(encoding="utf-8", errors="replace") for f in dossier.rglob("*") if f.is_file()
    )


def test_aucune_cle_dans_les_journaux_le_cache_et_les_erreurs(tmp_path, monkeypatch, cfg, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", CLE_GEMINI)
    monkeypatch.setenv("GROQ_API_KEY", CLE_GROQ)
    c = MockLLMClient(
        cfg,
        profile="prod",
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        quota_journal=tmp_path / "quotas.json",
    )
    fuite = f"429 {CLE_GEMINI} https://x.invalid/?key={CLE_GEMINI} Bearer {CLE_GROQ}"
    c.mock.push(ProviderError("quota", fuite, 429), model=cfg.models["main"])
    c.complete(MSG, date_donnees=T, agent="macro")  # relayé vers le modèle de repli
    # Une erreur remontée à l'appelant ne contient pas la clé non plus.
    c.mock.push(ProviderError("bad_request", fuite, 400))
    with caplog.at_level(logging.DEBUG), pytest.raises(ProviderError) as e:
        c.complete(MSG, date_donnees=date(2024, 2, 2))
    assert CLE_GEMINI not in str(e.value) and CLE_GROQ not in str(e.value)
    for contenu in (_tout_le_texte(tmp_path), caplog.text, repr(c.records)):
        assert CLE_GEMINI not in contenu and CLE_GROQ not in contenu
    assert any(r.erreur for r in c.records)


def test_la_cle_n_entre_pas_dans_la_cle_de_cache(tmp_path, monkeypatch, cfg):
    def cle():
        c = MockLLMClient(
            cfg, profile="prod", cache_dir=tmp_path / "c", quota_journal=tmp_path / "q.json"
        )
        return c.complete(MSG, date_donnees=T).record.cle_cache

    monkeypatch.setenv("GEMINI_API_KEY", CLE_GEMINI)
    a = cle()
    monkeypatch.setenv("GEMINI_API_KEY", "autre-valeur-1234567")
    assert a == cle()


def test_enregistrement_d_appel_ne_contient_que_des_champs_declares(tmp_path, cfg):
    c = MockLLMClient(
        cfg,
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "c",
        quota_journal=tmp_path / "q.json",
    )
    c.complete(MSG, date_donnees=T)
    ligne = json.loads((tmp_path / "run" / "calls.jsonl").read_text().splitlines()[0])
    assert not any("key" in k.lower() or "secret" in k.lower() for k in ligne)
