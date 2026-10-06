"""Revue indépendante D-062 : que deviennent `PromptTronque` et les champs de journal dans les
agents et le débat (sans modifier agents/ ni debate/) ?"""

from __future__ import annotations

import json

import pytest
from agents_helpers import fabrique_ctx
from debate_helpers import scripte

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.macro import MacroAgent
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.debate.run import executer
from amundi_agentic.llm.types import LLMError, PromptTronque, ProviderError, RawCompletion

CLASSES = ["actions_etats_unis", "souverain_euro", "or"]


def tronquer_a_partir(ctx, n_appel=1, tokens=50, agent=None):
    """Le transport simulé renvoie `tokens` jetons évalués à partir du n-ième appel (troncature)."""
    mock = ctx.llm.mock
    original = mock.completion
    etat = {"n": 0}

    def completion(**kw):
        etat["n"] += 1
        r = original(**kw)
        if etat["n"] >= n_appel and (agent is None or agent in kw["messages"][0]["content"]):
            return RawCompletion(r.text, r.model_served, tokens, r.tokens_out)
        return r

    mock.completion = completion


def ctx_dev(tmp_path, **kw):
    return fabrique_ctx(tmp_path, handler=scripte(lambda r, t, a: 1), **kw)


def test_les_prompts_des_agents_depassent_le_seuil_de_controle(tmp_path):
    """Précondition : un prompt d'agent réel est assez long (> 1 000 jetons estimés) pour être
    contrôlé ; sinon la détection ne protégerait pas les agents."""
    ctx = ctx_dev(tmp_path)
    MacroAgent().analyse(ctx, CLASSES)
    chars = sum(len(m["content"]) for m in ctx.appels[0].messages)
    seuil = ctx.llm.config.truncation_check
    assert chars / seuil.chars_per_token >= seuil.min_estimated_tokens, chars


def test_un_agent_ne_masque_pas_la_troncature_elle_remonte_sans_vue_inventee(tmp_path):
    ctx = ctx_dev(tmp_path)
    tronquer_a_partir(ctx, 1, 50)
    with pytest.raises(PromptTronque):
        MacroAgent().analyse(ctx, CLASSES)
    assert ctx.rejets == [] or all("tronqu" not in r.motif for r in ctx.rejets)
    assert not list(ctx.llm.cache.directory.glob("??/*.json"))  # rien en cache


def test_les_captures_de_llmerror_relancent(tmp_path):
    """`base.py` et `simple_call.py` capturent `LLMError` pour la RELANCER (`raise`) : vérifié."""
    import inspect

    from amundi_agentic.agents import base, simple_call

    for mod in (base, simple_call):
        src = inspect.getsource(mod)
        i = src.index("except LLMError:")
        assert src[i : i + 80].replace(" ", "").splitlines()[1].startswith("raise")


def test_le_debat_laisse_remonter_la_troncature_pendant_la_collaboration(tmp_path):
    ctx = ctx_dev(tmp_path)
    tronquer_a_partir(ctx, 1, 50)
    votants = construire_votants(ctx, "allocation", live=False)
    esg = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    with pytest.raises(PromptTronque):
        run_debate(ctx, "allocation", CLASSES, votants, Coordinator(), esg, risk_agent=RiskAgent())


def test_le_debat_ne_traite_pas_la_troncature_en_revision_comme_une_panne(tmp_path):
    """Le débat conserve le vote précédent sur `ProviderError` (panne) : une troncature (`LLMError`
    qui n'est pas une `ProviderError`) n'est PAS capturée : le débat s'arrête (comportement voulu :
    ne pas continuer sur des prompts tronqués)."""
    ctx = fabrique_ctx(tmp_path, handler=scripte(lambda r, t, a: -1 if "Macro" in r else 1))
    mock = ctx.llm.mock
    original = mock.completion

    def completion(**kw):
        r = original(**kw)
        if "Tour de débat" in kw["messages"][0]["content"]:
            return RawCompletion(r.text, r.model_served, 50, r.tokens_out)
        return r

    mock.completion = completion
    votants = construire_votants(ctx, "allocation", live=False)
    esg = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    with pytest.raises(PromptTronque):
        run_debate(ctx, "allocation", CLASSES, votants, Coordinator(), esg, risk_agent=RiskAgent())


@pytest.mark.xfail(
    strict=True,
    reason="IMPORTANT (non bloquant) : `executer` (debate/run.py) ne capture ni PromptTronque ni "
    "LLMError : la commande `views` plante avec une trace et AUCUN journal, alors que les débats "
    "déjà terminés pourraient être gardés (comme pour ProviderError) ; il faudrait un échec "
    "propre « débat non terminé : prompt tronqué (D-062) » et un code de sortie dédié",
)
def test_executer_transforme_la_troncature_en_debat_non_termine_sans_perdre_le_reste(tmp_path):
    ctx = ctx_dev(tmp_path)
    tronquer_a_partir(ctx, 8, 50)  # les premiers appels passent, puis troncature
    sortie = executer(ctx, classes=CLASSES, titres=[], live=False)
    assert sortie.echecs and "tronqu" in json.dumps(sortie.echecs, ensure_ascii=False).lower()


def test_la_troncature_est_un_llmerror_pas_un_providererror_donc_ni_relais_ni_panne():
    assert issubclass(PromptTronque, LLMError) and not issubclass(PromptTronque, ProviderError)


# --------------------------------------------------------------------------- journal du débat
def test_le_journal_du_debat_transmet_les_trois_champs_d_un_run_avec_mock(tmp_path):
    ctx = ctx_dev(tmp_path)
    votants = construire_votants(ctx, "allocation", live=False)
    esg = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    res = run_debate(
        ctx, "allocation", CLASSES, votants, Coordinator(), esg, risk_agent=RiskAgent()
    )
    appels = res.log.appels
    assert appels
    for a in appels:
        r = a.record
        assert r.prompt_tokens_estimes is not None and r.prompt_tokens_estimes >= 0
        assert r.prompt_tokens_evalues is not None and r.num_ctx == 16384  # profil dev : Ollama
    # ces champs survivent à la sérialisation du journal complet
    brut = json.loads(res.log.model_dump_json())
    assert all(
        "num_ctx" in x["record"] and "prompt_tokens_estimes" in x["record"] for x in brut["appels"]
    )
    from amundi_agentic.schemas import DebateLog

    assert DebateLog.model_validate_json(res.log.model_dump_json()) == res.log


def test_calls_jsonl_d_un_debat_contient_les_memes_champs(tmp_path):
    ctx = ctx_dev(tmp_path)
    MacroAgent().analyse(ctx, CLASSES)
    ligne = json.loads((tmp_path / "run" / "calls.jsonl").read_text().splitlines()[0])
    assert ligne["num_ctx"] == 16384 and ligne["prompt_tokens_estimes"] > 0
    assert ligne["prompt_tokens_evalues"] == ligne["tokens_entree"]


def test_cache_hit_d_un_debat_n_a_pas_de_champs_de_troncature(tmp_path):
    ctx = ctx_dev(tmp_path)
    MacroAgent().analyse(ctx, CLASSES)
    ctx2 = ctx_dev(tmp_path)  # même cache
    MacroAgent().analyse(ctx2, CLASSES)
    hits = [r for r in ctx2.llm.records if r.cache_hit]
    assert hits and all(
        (r.prompt_tokens_evalues, r.prompt_tokens_estimes, r.num_ctx) == (None, None, None)
        for r in hits
    )
