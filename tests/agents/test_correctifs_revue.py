"""Correctifs de la revue : nombres en lettres, décimales déguisées, échelle selon l'unité,
tolérance relative des entiers, ancrage par actif (nouveaux tests, aucun test existant touché)."""

from __future__ import annotations

import json

import pytest
from agents_helpers import fabrique_ctx

from amundi_agentic.agents.grounding import Ancre, chiffres_non_ancres
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.agents.valuation import ValuationAgent

CFG = load_settings().grounding
A, B = "actions_etats_unis", "or"


def refuse(texte, *valeurs):
    return bool(chiffres_non_ancres([texte], list(valeurs), CFG))


@pytest.mark.parametrize(
    "texte",
    [
        "rendement de douze pour cent",
        "gain de douze virgule sept pour cent",
        "twelve percent",
        "twelve point seven percent",
        "vingt et un pour cent",
        "gain de twenty one",  # avec mot de contexte financier (sans contexte : accepté, cf. v2)
        "quatre-vingt-dix points de base",
        "ratio de 12 virgule 7",
        "ratio de 12 point 7",
        "ratio de 12 comma 7",
        "ratio de 12 dot 7",
        "ratio de douze virgule sept",
        "ratio de 12٫7",
        "ratio de 12·7",
        "ratio de 12'7",
        "ratio de 12’7",
        "ratio de 12 7",
        "ratio de ١٢,٧",
        "deux millions de dollars",
    ],
)
def test_nombres_deguises_sont_controles_et_rejetes_si_absents(texte):
    assert refuse(texte, Ancre(0.999, "outil"))


@pytest.mark.parametrize(
    "texte,ancre",
    [
        ("douze pour cent", Ancre(0.12)),
        ("twelve percent", Ancre(0.12)),
        ("douze virgule sept pour cent", Ancre(0.127)),
        ("twelve point seven percent", Ancre(0.127)),
        ("ratio de 12 virgule 7", Ancre(12.7)),
        ("ratio de 12٫7", Ancre(12.7)),
        ("vingt et un pour cent", Ancre(0.21)),
        ("deux millions de dollars", Ancre(2_000_000.0)),
        ("revenu de 1,234", Ancre(1234.0)),  # séparateur de milliers ambigu : deux lectures
        ("revenu de 1,234", Ancre(1.234)),
    ],
)
def test_nombres_deguises_retrouves_dans_les_ancrages_sont_acceptes(texte, ancre):
    assert not refuse(texte, ancre)


@pytest.mark.parametrize(
    "texte",
    [
        "trois analystes",
        "un risque",
        "une hausse",
        "one analyst",
        "six mois",
        "dix jours",
        "le point de vue",
        "au point mort",
        "depuis 2023",
    ],
)
def test_petits_entiers_banals_en_lettres_restent_acceptes(texte):
    assert not refuse(texte)


def test_echelle_selon_l_unite_pour_les_ancrages_types():
    assert refuse("rendement de 5 %", Ancre(5.0, "outil"))  # un ratio de 5 n'est pas 5 %
    assert not refuse("rendement de 5 %", Ancre(0.05, "outil"))
    assert not refuse("marge de 5 %", Ancre(5.0, "texte"))  # lu tel quel dans un texte source
    assert refuse("ratio de 0,05", Ancre(5.0, "outil"))
    assert not refuse("écart de 25 pb", Ancre(0.0025, "outil"))
    assert refuse("écart de 25 %", Ancre(0.0025, "outil"))


def test_tolerance_relative_des_entiers():
    # 12,9 % cité « 13 % » : écart 0,1 < 1 % de 13 (0,13) ; 13,35 % cité « 13 % » : refusé
    assert not refuse("rendement de 13 %", Ancre(0.129))
    assert refuse("rendement de 13 %", Ancre(0.1335))
    assert refuse("rendement de 13 %", Ancre(0.1304 + 0.0036))
    assert CFG.tolerance_relative_entiers < 0.5 / 13


def test_valeur_d_un_autre_actif_refusee_par_l_ancrage_par_actif(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    ev = ValuationAgent("allocation").collecter(ctx, [A, B])
    propres = set(ev.pour([A]).valeurs())
    de_b = sorted(v for v in set(ev.pour([B]).valeurs()) if 0.01 < v < 1 and v not in propres)
    texte = f"La volatilité vaut {round(de_b[0] * 100, 1)} %.".replace(".", ",", 1)
    assert chiffres_non_ancres([texte], ev.ancres_pour(A), CFG)
    assert not chiffres_non_ancres([texte], ev.ancres_pour(B), CFG)

    def forge(model, messages):
        out = json.loads(politique_simulee(model, messages))
        for v in out["vues"]:
            if v["actif"] == A:
                v["arguments_pour"] = [texte]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path / "x", handler=forge)
    r = ValuationAgent("allocation").analyse(ctx, [A, B])
    assert [v.actif for v in r.turn.vues] == [B]  # la vue sur A est rejetée, celle sur B acceptée
    assert any(A in rej.actifs for rej in r.rejets)


def test_valeur_transversale_macro_reste_citable_pour_tous_les_actifs(tmp_path):
    from amundi_agentic.agents.macro import MacroAgent

    ctx = fabrique_ctx(tmp_path)
    ev = MacroAgent().collecter(ctx, [A, B])
    commun = ev.ancres_pour(A)
    assert commun and {x.valeur for x in commun} == {x.valeur for x in ev.ancres_pour(B)}
