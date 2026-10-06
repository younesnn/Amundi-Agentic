# ruff: noqa: E501
"""Lecture et validation de `config/text_tools.yaml` (RAG, résumé, évaluation du RAG).

Les noms de modèles ne figurent pas ici : ils vivent dans `config/llm.yaml` (D-008).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from amundi_agentic.data.settings import CONFIG_DIR
from amundi_agentic.llm.types import PromptRef

ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = ROOT / "agent_prompts"


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Prefixes(_Cfg):
    document: str = ""
    query: str = ""


class RagConfig(_Cfg):
    forms: tuple[str, ...] = ("10-K", "10-Q")
    max_filings: int = Field(default=4, ge=1)
    chunk_chars: int = Field(default=1800, ge=200)
    overlap_chars: int = Field(default=200, ge=0)
    min_chunk_chars: int = Field(default=80, ge=1)
    min_section_chars: int = Field(default=400, ge=1)
    toc_gap_chars: int = Field(default=1500, ge=100)
    max_preamble_chars: int = Field(default=80_000, ge=1000)
    min_substantial_sections: int = Field(default=3, ge=1)
    embed_batch: int = Field(default=16, ge=1)
    prefixes: dict[str, Prefixes] = Field(default_factory=dict)


class SummaryConfig(_Cfg):
    max_items: int = Field(default=25, ge=1)
    max_chars_per_item: int = Field(default=700, ge=100)


class RagEvalConfig(_Cfg):
    judge_tier: str = "light"
    answer_tier: str = "light"
    max_passage_chars: int = Field(default=1200, ge=200)


class TextToolsConfig(_Cfg):
    rag: RagConfig = RagConfig()
    summary: SummaryConfig = SummaryConfig()
    rag_eval: RagEvalConfig = RagEvalConfig()


def load_text_tools_config(path: Path | None = None) -> TextToolsConfig:
    fichier = path or CONFIG_DIR / "text_tools.yaml"
    return TextToolsConfig.model_validate(yaml.safe_load(fichier.read_text(encoding="utf-8")))


def prompt_ref(nom: str, prompts_dir: Path | None = None) -> tuple[PromptRef, str]:
    """(référence versionnée, texte) d'un fichier `agent_prompts/<nom>_v<k>.md`. Le hash est celui
    des octets du fichier : il est enregistré avec chaque exécution (EX-O1-06)."""
    fichier = (prompts_dir or PROMPTS_DIR) / f"{nom}.md"
    octets = fichier.read_bytes()
    version = nom.rsplit("_v", 1)[-1] if "_v" in nom else "0"
    ref = PromptRef(
        prompt_id=nom.rsplit("_v", 1)[0],
        version=f"v{version}",
        sha256=hashlib.sha256(octets).hexdigest(),
    )
    return ref, octets.decode("utf-8")
