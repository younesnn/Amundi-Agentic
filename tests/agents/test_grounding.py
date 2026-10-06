"""Contrôle d'ancrage : aucun chiffre non retrouvé dans les sorties d'outils n'est accepté ; toute
source citée doit exister parmi les sorties d'outils du tour ; redemandes bornées puis rejet motivé."""

from __future__ import annotations

import json
import re

import pytest
from agents_helpers import fabrique_ctx

from amundi_agentic.agents.grounding import (
    chiffres_non_ancres,
    est_ancre,
    extraire_chiffres,
    valeurs_ancrage,
)
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.agents.valuation import ValuationAgent

CFG = load_settings().grounding
CLASSES = ["actions_etats_unis", "or"]


def ok(texte: str, valeurs: list[float]) -> bool:
    return not chiffres_non_ancres([texte], valeurs, CFG)


def test_pourcentage_decimal_et_arrondi():
    assert ok("rendement de 12,3 %", [0.1234])  # 12,34 % arrondi à 12,3
    assert ok("volatilité de 12,34 %", [0.1234])
    assert ok("ratio de 0.2314", [0.2314])
    assert ok("ratio de 0,23", [0.2314])
    assert not ok("rendement de 13 %", [0.1234])
    assert not ok(
        "rendement de 12,5 %", [0.1234]
    )  # au-delà de la demi-unité de la dernière décimale


def test_signe_ignore_et_points_de_base():
    assert ok("baisse de 5 %", [-0.05])
    assert ok("écart de 25 pb", [0.0025])
    assert not ok("écart de 30 pb", [0.0025])


def test_dates_annees_et_entiers_nus_non_controles():
    assert ok("depuis le 2024-02-01, sur 3 mois, moyenne mobile 200 jours, momentum 12-1", [])
    assert ok("en 2023", [])
    assert not ok("sur 3,5 mois", [])  # une décimale se contrôle toujours


def test_separateurs_francais_et_anglais():
    assert ok("revenu de 1 234 567 $", [1234567.0])
    assert ok("revenu de 1,234,567 $", [1234567.0])
    assert ok("marge de -14,5 %", [14.5])  # chiffre d'un texte source : échelle 1


def test_valeurs_d_ancrage_recursives_et_nan_ignores():
    v = valeurs_ancrage({"a": [1.5, {"b": float("nan")}], "t": "marge 14,5 %"})
    assert 1.5 in v and 14.5 in v and all(x == x for x in v)


def test_est_ancre_unitaire():
    (c,) = extraire_chiffres("volatilité 28,5 %", CFG)
    assert est_ancre(c, [0.285], CFG) and not est_ancre(c, [0.2], CFG)


# ------------------------------------------------------------------ au niveau de l'agent
def _valeur_outil(messages) -> float:
    contenu = "\n".join(m["content"] for m in messages if m["role"] == "user")
    return float(re.search(r'"volatilite_annualisee": ([0-9.e-]+)', contenu).group(1))


def test_chiffre_issu_de_l_outil_accepte(tmp_path):
    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        vol = _valeur_outil(messages)
        for v in out["vues"]:
            v["arguments_pour"] = [f"La volatilité annualisée vaut {vol * 100:.1f} %."]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    r = ValuationAgent("allocation").analyse(ctx, CLASSES[:1])
    assert len(r.turn.vues) == 1 and r.rejets == []


def test_llm_qui_invente_un_chiffre_est_rejete(tmp_path):
    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        for v in out["vues"]:
            v["arguments_pour"] = ["Le rendement annualisé atteint 87,65 % sur la période."]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    r = ValuationAgent("allocation").analyse(ctx, CLASSES)
    assert r.turn.vues == []  # aucune vue acceptée
    assert {a for rej in r.rejets for a in rej.actifs} == set(CLASSES)
    assert all("87,65" in rej.motif for rej in r.rejets)
    # redemandes bornées : 1 appel initial + max_retries
    assert len(ctx.appels) == ctx.settings.grounding.max_retries + 1
    assert all(rej.tentatives == ctx.settings.grounding.max_retries + 1 for rej in r.rejets)


def test_correction_apres_redemande(tmp_path):
    etat = {"n": 0}

    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        etat["n"] += 1
        if etat["n"] == 1:  # premier essai : chiffre inventé ; la redemande corrige
            for v in out["vues"]:
                v["arguments_contre"] = ["Perte maximale de 99,99 %."]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    r = ValuationAgent("allocation").analyse(ctx, CLASSES[:1])
    assert len(r.turn.vues) == 1 and r.rejets == []
    assert len(ctx.appels) == 2
    assert "refusée par le contrôle d'ancrage" in ctx.appels[1].messages[-1]["content"]


def test_source_inexistante_rejetee(tmp_path):
    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        for v in out["vues"]:
            v["source_ids"] = ["source-inventee"]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    r = ValuationAgent("allocation").analyse(ctx, CLASSES[:1])
    assert r.turn.vues == [] and "source_id inexistant" in r.rejets[0].motif


def test_sortie_non_json_rejetee_avec_motif(tmp_path):
    ctx = fabrique_ctx(tmp_path, handler=lambda m, msgs: "pas du json")
    r = ValuationAgent("allocation").analyse(ctx, CLASSES[:1])
    assert r.turn.vues == [] and "schéma" in r.rejets[0].motif


@pytest.mark.parametrize("texte", ["rendement de 55 %", "sharpe de 3,21"])
def test_chiffre_inconnu_dans_argument_contre_aussi_controle(tmp_path, texte):
    def handler(model, messages):
        out = json.loads(politique_simulee(model, messages))
        for v in out["vues"]:
            v["arguments_contre"] = [texte]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    assert ValuationAgent("allocation").analyse(ctx, CLASSES[:1]).turn.vues == []
