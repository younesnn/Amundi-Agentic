"""Revue indépendante : ancrage aux tours de révision (valeurs et sources des pairs, avocat du
diable). Un chiffre ou une source n'est utilisable que s'il vient des sorties d'outils de l'agent,
ou d'un pair déjà validé (tour précédent)."""

from __future__ import annotations

import json

from agents_helpers import fabrique_ctx

from amundi_agentic.agents.macro import MacroAgent
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.valuation import ValuationAgent

A = "actions_etats_unis"


def _ctx_avec(tmp_path, texte_pair, reponse_macro):
    """Contexte où Valuation (tour 0) écrit `texte_pair` et Macro (révision) renvoie `reponse_macro`."""

    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        systeme = messages[0]["content"]
        if "Agent Valuation" in systeme and "vues" in out:
            for v in out["vues"]:
                v["arguments_pour"] = [texte_pair]
        if "Agent Macro" in systeme and "Tour de débat" in systeme:
            out = reponse_macro(out)
        return json.dumps(out, ensure_ascii=False)

    return fabrique_ctx(tmp_path, handler=handler)


def _revision(ctx, devil=False):
    val = ValuationAgent("allocation").analyse(ctx, [A])
    assert val.turn.vues, val.rejets
    res = MacroAgent().revise(ctx, [A], [val.turn], {A: 0}, tour=1, devil=devil)
    return val, res


def test_la_revision_peut_reprendre_un_chiffre_valide_d_un_pair(tmp_path):
    ctx0 = fabrique_ctx(tmp_path / "p")
    ev = ValuationAgent("allocation").evidence(ctx0, [A])
    vol = next(v for v in sorted(set(ev.valeurs())) if 0.15 < v < 0.35)
    chiffre = f"{vol * 100:.1f} %"
    ctx = _ctx_avec(
        tmp_path / "x",
        f"La volatilité annualisée vaut {chiffre}.",
        lambda out: {
            **out,
            "vues": [
                {**v, "arguments_pour": [f"Le pair relève une volatilité de {chiffre}."]}
                for v in out["vues"]
            ],
        },
    )
    _, res = _revision(ctx)
    assert len(res.turn.vues) == 1 and res.rejets == []


def test_la_revision_ne_peut_pas_inventer_un_chiffre_meme_avec_des_pairs(tmp_path):
    ctx = _ctx_avec(
        tmp_path,
        "Argument sans chiffre.",
        lambda out: {
            **out,
            "vues": [{**v, "arguments_pour": ["rendement de 12,7 %"]} for v in out["vues"]],
        },
    )
    _, res = _revision(ctx)
    assert res.turn.vues == [] and "introuvables" in res.rejets[0].motif


def test_un_chiffre_du_pair_n_est_pas_disponible_au_tour_zero(tmp_path):
    """Aux seuls tours d'analyse, les textes des pairs ne sont pas des ancrages."""
    ctx0 = fabrique_ctx(tmp_path / "p")
    ev = ValuationAgent("allocation").evidence(ctx0, [A])
    vol = next(v for v in sorted(set(ev.valeurs())) if 0.15 < v < 0.35)
    # ce chiffre vient de Valuation, pas de Macro : Macro ne peut pas le citer au tour 0
    ctx = fabrique_ctx(
        tmp_path / "x",
        handler=lambda m, msgs: json.dumps(
            {
                **json.loads(politique_simulee(m, msgs)),
                "vues": [
                    {
                        **v,
                        "arguments_pour": [f"volatilité de {vol * 100:.2f} %"],
                    }
                    for v in json.loads(politique_simulee(m, msgs)).get("vues", [])
                ],
            }
        ),
    )
    r = MacroAgent().analyse(ctx, [A])
    assert r.turn.vues == []


def test_la_source_d_un_pair_est_citable_en_revision_pas_au_tour_zero(tmp_path):
    ctx0 = fabrique_ctx(tmp_path / "p")
    sid_valuation = sorted(ValuationAgent("allocation").evidence(ctx0, [A]).ids())[0]

    def macro_cite_la_source_du_pair(out):
        return {**out, "vues": [{**v, "source_ids": [sid_valuation]} for v in out["vues"]]}

    ctx = _ctx_avec(tmp_path / "x", "Argument sans chiffre.", macro_cite_la_source_du_pair)
    _, res = _revision(ctx)
    assert len(res.turn.vues) == 1  # autorisée en révision
    ctx2 = fabrique_ctx(
        tmp_path / "y",
        handler=lambda m, msgs: json.dumps(
            {
                **json.loads(politique_simulee(m, msgs)),
                "vues": [
                    {**v, "source_ids": [sid_valuation]}
                    for v in json.loads(politique_simulee(m, msgs)).get("vues", [])
                ],
            }
        ),
    )
    r0 = MacroAgent().analyse(ctx2, [A])
    assert r0.turn.vues == [] and "source_id inexistant" in r0.rejets[0].motif


def test_source_d_un_tour_precedent_inconnue_de_l_agent_rejetee(tmp_path):
    ctx = _ctx_avec(
        tmp_path,
        "Argument sans chiffre.",
        lambda out: {
            **out,
            "vues": [{**v, "source_ids": ["source-du-tour-0"]} for v in out["vues"]],
        },
    )
    _, res = _revision(ctx)
    assert res.turn.vues == [] and "inexistant" in res.rejets[0].motif


# --------------------------------------------------------------------------- avocat du diable
def _avocat(objection, sources):
    def f(out):
        return {
            **out,
            "objection": objection,
            "objection_source_ids": sources,
        }

    return f


def _sid(tmp_path):
    return sorted(ValuationAgent("allocation").evidence(fabrique_ctx(tmp_path / "s"), [A]).ids())[0]


def test_objection_avec_chiffre_invente_rejetee_et_vote_conserve(tmp_path):
    sid = _sid(tmp_path)
    ctx = _ctx_avec(
        tmp_path / "x",
        "Argument sans chiffre.",
        _avocat("La position majoritaire ignore une perte de 45,6 %.", [sid]),
    )
    _, res = _revision(ctx, devil=True)
    assert res.turn.objection is None and res.turn.role == "normal"
    assert any(r.actifs == [] and "objection" in r.motif for r in res.rejets)


def test_objection_sans_source_ou_avec_source_inventee_rejetee(tmp_path):
    for sources in ([], ["inventee"]):
        ctx = _ctx_avec(
            tmp_path / f"x{len(sources)}", "Argument sans chiffre.", _avocat("Objection.", sources)
        )
        _, res = _revision(ctx, devil=True)
        assert res.turn.objection is None, sources
        assert any("source_id" in r.motif for r in res.rejets)


def test_objection_absente_ou_blanche_rejetee_pour_l_avocat(tmp_path):
    for obj in (None, "", "   "):
        ctx = _ctx_avec(
            tmp_path / f"o{bool(obj)}{len(obj or '')}", "x", _avocat(obj, [_sid(tmp_path)])
        )
        _, res = _revision(ctx, devil=True)
        assert res.turn.objection is None
        assert any("objection obligatoire" in r.motif for r in res.rejets)


def test_objection_valide_conservee_et_un_non_avocat_ne_peut_pas_en_produire(tmp_path):
    sid = _sid(tmp_path)
    ctx = _ctx_avec(tmp_path / "a", "x", _avocat("Objection sans chiffre.", [sid]))
    _, res = _revision(ctx, devil=True)
    assert res.turn.objection == "Objection sans chiffre." and res.turn.role == "avocat_du_diable"
    ctx2 = _ctx_avec(tmp_path / "b", "x", _avocat("Objection non demandée.", [sid]))
    _, res2 = _revision(ctx2, devil=False)
    assert res2.turn.objection is None and res2.turn.role == "normal"
