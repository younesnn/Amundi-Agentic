"""Agents Fundamental (RAG) et Sentiment (résumé avec réflexion) : outils de la tâche A via les
protocoles de `agents/ports.py`, implémentations factices ici."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agents_helpers import T, fabrique_ctx

from amundi_agentic.agents.fundamental import FundamentalAgent
from amundi_agentic.agents.ports import (
    FakeNewsSummaryTool,
    FakePassage,
    FakeRagTool,
    NewsSummaryTool,
    RagTool,
)
from amundi_agentic.agents.providers import rag_synthetique
from amundi_agentic.agents.sentiment import SentimentAgent
from amundi_agentic.schemas import Source


def test_les_fakes_satisfont_les_protocoles():
    assert isinstance(FakeRagTool(), RagTool)
    assert isinstance(FakeNewsSummaryTool(), NewsSummaryTool)


def test_fundamental_interroge_le_rag_avec_les_questions_du_papier(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ctx.rag = rag_synthetique(T, ["AAA"])
    r = FundamentalAgent().analyse(ctx, ["AAA"])
    questions = ctx.settings.fundamental.questions
    assert [q[1] for q in ctx.rag.queries] == questions  # type: ignore[attr-defined]
    assert ctx.rag.indexed == [("AAA", T)]  # type: ignore[attr-defined]
    assert all(q[2] == T and q[3] == ctx.settings.fundamental.rag_k for q in ctx.rag.queries)  # type: ignore[attr-defined]
    outils = [a.outil for a in r.turn.appels_outils]
    assert outils.count("rag_query") == len(questions) and "xbrl_facts" in outils
    (vue,) = r.turn.vues
    assert vue.sources and {s.type for s in vue.sources} <= {"depot_sec", "sortie_outil"}


def test_passage_date_a_t_ou_apres_est_ecarte(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    futur = Source(
        source_id="depot:futur",
        type="depot_sec",
        titre="10-K futur",
        reference="x",
        date_publication=datetime(
            2024, 1, 31, 23, 0, tzinfo=UTC
        ),  # = coupure (t 00:00 Paris, UTC-1)
        extrait="texte",
    )
    ctx.rag = FakeRagTool(passages={"AAA": [FakePassage("texte futur", "Item 7", 0.9, futur)]})
    ev = FundamentalAgent().collecter(ctx, ["AAA"])
    assert "depot:futur" not in ev.ids()
    assert any("sans réponse" in v for v in ev.manquants.values())


def test_fundamental_sans_rag_s_abstient_sans_appel_llm(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ctx.rag = None
    # les faits XBRL synthétiques restent citables : désactivés pour isoler le cas
    ctx.data.xbrl_facts = lambda ticker: None  # type: ignore[method-assign]
    r = FundamentalAgent().analyse(ctx, ["AAA"])
    assert r.turn.vues == [] and r.rejets and "outil" in r.rejets[0].motif
    assert ctx.appels == []


def test_sentiment_appelle_le_resume_en_light_et_porte_son_toolcall(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    r = SentimentAgent("titre").analyse(ctx, ["AAA"])
    (appel,) = ctx.summarizer.appels  # type: ignore[attr-defined]
    assert appel["tier"] == "light" and appel["as_of"] == T
    assert "société" in appel["focus"] and appel["n_items"] > 0
    assert [a.outil for a in r.turn.appels_outils] == ["news_summary"]
    assert r.turn.vues and all(
        s.date_publication < datetime(2024, 2, 1, tzinfo=UTC) for s in r.turn.vues[0].sources
    )


def test_sentiment_allocation_filtre_par_termes_macro(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    requetes = []
    vrai = ctx.data.news
    ctx.data.news = lambda q: (requetes.append(q), vrai(q))[1]  # type: ignore[method-assign]
    SentimentAgent("allocation").analyse(ctx, ["actions_etats_unis"])
    assert requetes[0].terms == tuple(ctx.settings.sentiment.termes_allocation)
    assert requetes[0].start == T - timedelta(days=ctx.settings.sentiment.fenetre_jours)


def test_sentiment_sans_news_s_abstient_sans_appel_llm(tmp_path):
    ctx = fabrique_ctx(tmp_path, avec_news=False)
    r = SentimentAgent("titre").analyse(ctx, ["AAA"])
    assert r.turn.vues == [] and "couverture insuffisante" in r.rejets[0].motif
    assert ctx.appels == [] and ctx.summarizer.appels == []  # type: ignore[attr-defined]


def test_passage_identique_retrouve_par_plusieurs_questions_injecte_une_seule_fois(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ctx.rag = rag_synthetique(T, ["AAA"])  # mêmes passages pour chacune des 4 questions
    ev = FundamentalAgent().collecter(ctx, ["AAA"])
    ids = [e.source_id for e in ev.items if e.source_id and e.source_id.startswith("depot_sec")]
    assert len(ids) == len(set(ids)) == 3
    assert [a.outil for a in ev.appels()].count("rag_query") == 4  # un ToolCall par question
