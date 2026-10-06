"""Revue indépendante : compatibilité avec le RAG et le résumé de la tâche A (sur `main`)."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents_helpers import T, fabrique_ctx

from amundi_agentic.agents.fundamental import FundamentalAgent
from amundi_agentic.agents.ports import FakePassage, NewsSummaryTool, RagTool
from amundi_agentic.agents.providers import rag_synthetique


@dataclass
class ResultatAvecRepli:
    passages: tuple
    section_fallback: bool = True
    fallback_accessions: list[str] = field(default_factory=lambda: ["0000320193-23-000106"])


class RagEnRepli:
    """RAG dont le découpage par sections a échoué (repli « Document ») : contrat du vrai
    `FilingsRAG.query` (champs `section_fallback`, `fallback_accessions`)."""

    def __init__(self, base):
        self.base = base

    def index_filings(self, ticker, as_of):
        return self.base.index_filings(ticker, as_of)

    def query(self, ticker, question, as_of, *, k=5):
        res = self.base.query(ticker, question, as_of, k=k)
        passages = tuple(FakePassage(p.text, "Document", p.score, p.source) for p in res.passages)
        return ResultatAvecRepli(passages)


def test_les_ports_acceptent_les_signatures_du_vrai_rag_et_du_vrai_resume():
    from amundi_agentic.agents.ports import FakeNewsSummaryTool, FakeRagTool

    assert isinstance(FakeRagTool(), RagTool) and isinstance(FakeNewsSummaryTool(), NewsSummaryTool)


def test_fundamental_signale_un_decoupage_en_repli(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ctx.rag = RagEnRepli(rag_synthetique(T, ("AAA",)))
    r = FundamentalAgent().analyse(ctx, ["AAA"])
    prompt = ctx.appels[0].messages[1]["content"].lower()
    signale = "repli" in prompt or "fallback" in prompt or "0000320193-23-000106" in prompt
    dans_la_vue = any(
        "repli" in (a + c).lower() or "découpage" in (a + c).lower()
        for v in r.turn.vues
        for a, c in zip(v.arguments_pour, v.arguments_contre, strict=False)
    )
    assert signale or dans_la_vue
