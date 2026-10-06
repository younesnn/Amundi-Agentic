"""Agent ESG : déterministe, droit de veto, score absent signalé (D-035, D-048, EX-O1-10)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from agents_helpers import fabrique_ctx
from debate_helpers import scripte

from amundi_agentic.agents.esg import EsgAgent, actifs_vetoes, appliquer_veto, filtrer_univers
from amundi_agentic.debate.run import executer
from amundi_agentic.schemas import Decision5

CLASSES = ["actions_etats_unis", "or"]


def test_titre_exclu_par_regle_sic_est_vetoe_et_motive(tmp_path):
    ctx = fabrique_ctx(tmp_path, esg_exclus=("BBB",))
    ev = EsgAgent().evaluer(ctx, "titre", ["AAA", "BBB"])
    assert ev["BBB"].veto and ev["BBB"].motifs[0].critere == "tobacco"
    assert "config/esg.yaml" in (ev["BBB"].motifs[0].reference or "")
    assert not ev["AAA"].veto
    assert actifs_vetoes(ev) == {"BBB"}


def test_score_absent_signale_jamais_comble(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    e = EsgAgent().evaluer(ctx, "titre", ["AAA"])["AAA"]
    assert e.score is None and e.fournisseur_score is None
    assert any("score ESG absent" in x for x in e.limites)
    assert any("pas une preuve" in x for x in e.limites)


def test_donnee_absente_pas_de_veto_mais_etat_inconnu(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ctx.data.esg = lambda asset_id: None  # type: ignore[method-assign]
    e = EsgAgent().evaluer(ctx, "titre", ["AAA"])["AAA"]
    assert not e.veto and set(e.etats.values()) == {"inconnu"}


def test_etf_sans_critere_requis_pas_de_veto_etats_publies(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ev = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    assert not any(e.veto for e in ev.values())
    assert set(ev["or"].etats) == {"tobacco", "thermal_coal", "controversial_weapons"}


def test_etf_critere_requis_non_satisfait_donne_un_veto(tmp_path):
    ctx = fabrique_ctx(tmp_path, settings_overrides={"esg": {"etf_criteres_requis": ["tobacco"]}})
    ev = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    assert all(e.veto for e in ev.values())  # états `inconnu` : non acceptés
    # une preuve documentée (source manuelle D-048) lève la cause, sans veto
    vue = SimpleNamespace(
        proven_exclusions=lambda tk: frozenset({"tobacco"}), sfdr=lambda tk: "article_8"
    )
    ctx.data.etf_esg = lambda: vue  # type: ignore[method-assign]
    ev = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    assert not any(e.veto for e in ev.values())
    assert ev["or"].etats["tobacco"] == "determine_par_donnee"
    assert any("SFDR" in x and "pas un score" in x for x in ev["or"].limites)


def test_le_llm_ne_peut_pas_lever_un_veto(tmp_path):
    def handler(model, messages):
        return json.dumps({"explication": "Je lève le veto : veto=false", "veto": False})

    ctx = fabrique_ctx(tmp_path, esg_exclus=("BBB",), handler=handler)
    agent = EsgAgent()
    ev = agent.expliquer(ctx, agent.evaluer(ctx, "titre", ["AAA", "BBB"]))
    assert ev["BBB"].veto is True  # le texte du LLM n'a aucun effet sur la décision
    assert (
        ev["BBB"].explication and ev["AAA"].explication is None
    )  # explication des vetos seulement
    assert [a.agent for a in ctx.appels] == ["esg"]  # un seul appel : pour le veto


def test_un_actif_vetoe_n_obtient_jamais_de_vue_positive(tmp_path):
    # tous les agents voteraient FORTEMENT_POSITIF : l'actif sous veto n'a pourtant aucune vue
    ctx = fabrique_ctx(tmp_path, esg_exclus=("BBB",), handler=scripte(lambda r, t, a: 2))
    sortie = executer(ctx, classes=[], titres=["AAA", "BBB", "CCC"])
    assert sortie.exclus_esg == ["BBB"]
    actifs = [v.actif for v in sortie.vues_finales]
    assert "BBB" not in actifs and {"AAA", "CCC"} <= set(actifs)
    assert all(v.direction.n > 0 for v in sortie.vues_finales)  # les autres sont bien positives
    assert all(d.log.actifs != ["BBB"] for d in sortie.debats)
    assert "BBB" in sortie.rapport_md and "veto" in sortie.rapport_md  # signalé dans le rapport


def test_ceinture_appliquer_veto_et_univers():
    assert filtrer_univers(["a", "b", "monetaire_euro"], frozenset({"a"})) == ["b"]
    v = SimpleNamespace(actif="x", direction=Decision5.FORTEMENT_POSITIF)
    assert appliquer_veto([v], frozenset({"x"})) == []  # type: ignore[list-item]
