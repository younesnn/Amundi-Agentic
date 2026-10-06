"""Agents Macro, Valuation et Risque avec le LLM simulé (aucune clé, aucun réseau)."""

from __future__ import annotations

import json

import pytest
from agents_helpers import T, fabrique_ctx

from amundi_agentic.agents.macro import MacroAgent
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.agents.valuation import ValuationAgent

CLASSES = ["actions_etats_unis", "souverain_euro", "or"]


def test_valuation_produit_une_vue_par_classe_et_porte_ses_outils(ctx):
    r = ValuationAgent("allocation").analyse(ctx, CLASSES)
    assert [v.actif for v in r.turn.vues] == CLASSES
    assert r.rejets == []
    # chaque tour porte ses ToolCall, un par classe (EX-O1-04 : l'agent utilise bien ses outils)
    assert [a.outil for a in r.turn.appels_outils] == ["valuation_summary"] * 3
    for v in r.turn.vues:
        assert v.statut == "individuelle" and v.auteur == "valuation"
        assert v.profil_risque == "equilibre"
        # toute source citée existe parmi les sorties d'outils du tour
        ids = {a.resultat["meta"]["source_id"] for a in r.turn.appels_outils}
        assert {s.source_id for s in v.sources} <= ids
        assert all(s.type == "sortie_outil" for s in v.sources)
        assert v.rendement_excedentaire_attendu is None  # jamais écrit par le LLM


def test_les_toolcalls_sont_serialisables_en_json_strict(ctx):
    r = ValuationAgent("allocation").analyse(ctx, CLASSES[:1])
    json.dumps(r.turn.model_dump(mode="json"), allow_nan=False)


def test_macro_utilise_l_outil_de_regime(ctx):
    r = MacroAgent().analyse(ctx, CLASSES)
    assert [a.outil for a in r.turn.appels_outils] == ["macro_regime"]
    assert len(r.turn.vues) == 3


def test_le_prompt_contient_le_profil_et_les_regles_d_ancrage(ctx):
    ValuationAgent("allocation").analyse(ctx, CLASSES[:1])
    systeme = ctx.appels[0].messages[0]["content"]
    assert "équilibré" in systeme and "AUCUN chiffre" in systeme
    assert ctx.appels[0].prompt_id == "valuation_allocation+regles_communes"
    assert len(ctx.appels[0].prompt_sha256) == 64


def test_risque_alertes_calculees_par_python_pas_par_le_llm(tmp_path):
    def llm_malveillant(model, messages):
        # le LLM tente d'imposer une alerte : ignorée, le commentaire seul est retenu
        return json.dumps({"commentaire": "RAS", "alertes": {"or": "aucune"}})

    c1 = fabrique_ctx(tmp_path / "a", handler=llm_malveillant)
    r = RiskAgent().assess(c1, "allocation", CLASSES)
    sans_llm = RiskAgent().assess(c1, "allocation", CLASSES, commenter=False)
    assert r.assessment.alertes == sans_llm.assessment.alertes
    assert r.assessment.commentaire == "RAS"
    assert set(r.assessment.alertes) <= set(CLASSES)


def test_risque_commentaire_non_ancre_est_rejete_sans_toucher_aux_alertes(tmp_path):
    c = fabrique_ctx(
        tmp_path, handler=lambda m, msgs: json.dumps({"commentaire": "volatilité de 77,77 %"})
    )
    r = RiskAgent().assess(c, "allocation", CLASSES)
    assert r.assessment.commentaire == ""
    assert "77,77" in (r.commentaire_rejete or "")


@pytest.mark.parametrize("niveau", ["allocation"])
def test_aucune_donnee_posterieure_a_t(ctx, niveau):
    for a in CLASSES:
        assert ctx.data.class_prices(a).index.max() < __import__("pandas").Timestamp(T)
