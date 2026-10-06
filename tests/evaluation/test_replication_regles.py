# ruff: noqa: E501
"""Règles de rapport de D-065 §10 et formulations interdites de D-064, sur des cas construits."""

from __future__ import annotations

from datetime import date

import pytest

from amundi_agentic.evaluation import rapport as rp
from amundi_agentic.evaluation.repl_config import charger_config

CFG = charger_config()


def _c(contre, delta=0.05, bas=0.01, haut=0.09, diff=6, des=0.01):
    return {
        "pour": "multi_agent",
        "contre": contre,
        "delta": delta,
        "bas": bas,
        "haut": haut,
        "contient_zero": bas <= 0 <= haut,
        "titres_differents": diff,
        "desaccord_entre_executions": des,
    }


def _res(surcharge=None):
    surcharge = surcharge or {}
    """Résultats minimaux : toutes les conditions réunies sauf ce qui est surchargé par (profil, contre)."""
    out = {"executions": {"baseline": {}}}
    for pf in CFG.profils:
        comps = [_c("ET"), _c("OU"), _c("valuation_seul"), _c("fundamental_seul"), _c("ref15")]
        for i, c in enumerate(comps):
            if (pf, c["contre"]) in surcharge:
                comps[i] = {**c, **surcharge[(pf, c["contre"])]}
        out["executions"]["baseline"][pf] = {"comparaisons": comps}
    return out


def test_meilleur_seulement_si_tout_est_reuni_sur_les_deux_profils():
    v = rp.calculer_verdict(_res(), CFG)
    assert v.statut == "multi_agent_meilleur" and not v.raisons


def test_intervalle_contenant_zero_donne_non_concluant():
    v = rp.calculer_verdict(
        _res({("risk_averse", "ET"): {"bas": -0.01, "contient_zero": True}}), CFG
    )
    assert v.statut == "non_concluant" and any("contient 0" in r for r in v.raisons)


def test_moins_de_4_titres_differents_donne_non_concluant():
    v = rp.calculer_verdict(
        _res({("risk_neutral", "valuation_seul"): {"titres_differents": 3}}), CFG
    )
    assert v.statut == "non_concluant" and any("moins de 4" in r for r in v.raisons)
    v4 = rp.calculer_verdict(
        _res({("risk_neutral", "valuation_seul"): {"titres_differents": 4}}), CFG
    )
    assert v4.statut == "multi_agent_meilleur"


def test_ecart_inferieur_au_desaccord_donne_non_concluant():
    v = rp.calculer_verdict(
        _res({("risk_averse", "fundamental_seul"): {"desaccord_entre_executions": 0.06}}), CFG
    )
    assert v.statut == "non_concluant" and any("désaccord" in r for r in v.raisons)
    v = rp.calculer_verdict(
        _res({("risk_averse", "ET"): {"desaccord_entre_executions": None}}), CFG
    )
    assert v.statut == "non_concluant" and any("non mesurable" in r for r in v.raisons)


def test_multi_agent_ne_battant_pas_et_donne_non_concluant():
    v = rp.calculer_verdict(
        _res({("risk_averse", "ET"): {"delta": -0.05, "bas": -0.09, "haut": -0.01}}), CFG
    )
    assert v.statut == "non_concluant" and any("ne fait pas mieux" in r for r in v.raisons)


def test_un_profil_defaillant_suffit():
    v = rp.calculer_verdict(
        _res({("risk_neutral", "OU"): {}, ("risk_neutral", "ET"): {"titres_differents": 0}}), CFG
    )
    assert v.statut == "non_concluant"
    assert (
        v.par_profil["risk_averse"]["conditions_reunies"]
        and not v.par_profil["risk_neutral"]["conditions_reunies"]
    )


@pytest.mark.parametrize(
    "texte",
    [
        "Le multi-agent bat les agents seuls.",
        "Cela confirme les résultats d'AlphaAgents.",
        "Le débat réduit la pensée de groupe.",
        "une confiance calibrée",
        "la probabilité de succès",
        "un alpha positif",
        "une surperformance nette",
        "résultat robuste",
        "résultat validé",
        "portefeuille conforme ESG",
        "analyse fondamentale du titre",
        "prouve la qualité du raisonnement",
        "résultat hors échantillon pour Gemini",
    ],
)
def test_formulations_interdites_detectees(texte):
    assert rp.formulations_interdites(texte)


def test_formulations_autorisees_non_signalees():
    assert not rp.formulations_interdites("AlphaAgents est le papier. Verdict : non concluant.")
    assert not rp.formulations_interdites("hors échantillon sous réserve d'un sondage de mémoire")
    assert not rp.formulations_interdites("lecture qualitative de dépôts par un LLM")


def test_sharpe_sans_intervalle_refuse():
    bon = (
        "| Portefeuille | Sharpe [IC] |\n| --- | --- |\n| A | 0.50 [-1.00 ; 2.00] |\n| B | n/d |\n"
    )
    assert not rp.controler_sharpe_tableaux(bon)
    mauvais = "| Portefeuille | Sharpe |\n| --- | --- |\n| A | 0.50 |\n"
    assert rp.controler_sharpe_tableaux(mauvais)
    assert rp.fmt_sharpe(0.5, None) == "n/d"


def test_etiquettes_de_modele_lues_dans_training_cutoff():
    cut = {"gemini-x": date(2026, 3, 31), "llama-y": date(2023, 12, 31), "vieux": date(2023, 6, 30)}
    e = dict(
        rp.etiquette_modele(
            ["gemini/gemini-x", "ollama/llama-y", "ollama/inconnu"], cut, CFG, simule=False
        )
    )
    assert e["gemini/gemini-x"] == CFG.modele.etiquette_contamine
    # fin d'entraînement + 3 mois de marge (2024-03-31) >= décision (2024-02-01) : hors échantillon non garanti
    assert e["ollama/llama-y"] == CFG.modele.etiquette_marge
    assert dict(rp.etiquette_modele(["ollama/vieux"], cut, CFG, simule=False))["ollama/vieux"] == (
        CFG.modele.etiquette_hors_echantillon
    )
    assert e["ollama/inconnu"] == CFG.modele.etiquette_inconnue
    assert rp.etiquette_modele([], {}, CFG, simule=True)[0][1] == CFG.modele.etiquette_simule


@pytest.mark.parametrize(
    "texte",
    [
        "the multi-agent beats the single agents",
        "le multi\u2011agent bat",
        "Multi\u2013Agent   BAT les agents seuls",
        "outperforms the benchmark",
        "outperformance",
        "validated",
        "robust",
        "this proves it",
        "confirms AlphaAgents",
        "confirme les résultats du papier",
        "hors-échantillon",
        "hors\u00a0échantillon",
        "out-of-sample",
        "out of sample",
        "calibrated confidence",
        "la confiance est calibrée",
        "le multi-agent l'emporte sur les agents seuls",
        "ESG-compliant",
        "fundamental analysis",
        "analyses fondamentales",
        "sur performance",
        "réduit les biais de groupe",
    ],
)
def test_variantes_anglaises_tirets_et_paraphrases_detectees(texte):
    assert rp.formulations_interdites(texte), texte


def test_formules_d_etiquette_toujours_autorisees():
    for e in (CFG.modele.etiquette_hors_echantillon, CFG.modele.etiquette_marge):
        assert not rp.formulations_interdites(e), e
        assert not rp.formulations_interdites(e.upper())
    assert rp.formulations_interdites(CFG.modele.etiquette_marge + " donc hors échantillon")


def test_liste_interdite_vit_dans_la_config():
    import inspect

    assert len(CFG.rapport_interdit.motifs) >= 20
    assert "outperform" not in inspect.getsource(rp).split("def normaliser")[0]
