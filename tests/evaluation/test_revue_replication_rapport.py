# ruff: noqa: E501
"""Revue indépendante : verdict, rapport, formulations interdites, mock, reproductibilité, coût.

Aucun réseau, aucune clé, aucun Ollama : LLM simulé et données synthétiques seulement.
"""

from __future__ import annotations

import json
import re
import subprocess
from argparse import Namespace
from datetime import date

import pytest

from amundi_agentic.agents.settings import load_settings
from amundi_agentic.data.settings import ROOT
from amundi_agentic.evaluation import commande
from amundi_agentic.evaluation import rapport as rp
from amundi_agentic.evaluation.repl_config import charger_config
from amundi_agentic.llm import load_config

CFG = charger_config()


# ============================================================ verdict : chaque condition isolée
def _c(contre, delta=0.05, bas=0.01, haut=0.09, diff=6, des=0.01, pour="multi_agent"):
    return {
        "pour": pour,
        "contre": contre,
        "delta": delta,
        "bas": bas,
        "haut": haut,
        "contient_zero": bas <= 0 <= haut,
        "titres_differents": diff,
        "desaccord_entre_executions": des,
    }


def _res(modifs=None, profils=None):
    modifs = modifs or {}
    out = {"executions": {"baseline": {}}}
    for pf in profils or CFG.profils:
        comps = [_c(x) for x in ("ET", "OU", "valuation_seul", "fundamental_seul", "ref15")]
        comps = [{**c, **modifs.get((pf, c["contre"]), {})} for c in comps]
        out["executions"]["baseline"][pf] = {"comparaisons": comps}
    return out


def test_toutes_conditions_reunies_sur_les_deux_profils_donne_meilleur():
    v = rp.calculer_verdict(_res(), CFG)
    assert v.statut == "multi_agent_meilleur" and not v.raisons


@pytest.mark.parametrize(
    "modif,mot",
    [
        ({"bas": -0.001, "contient_zero": True}, "contient 0"),
        ({"titres_differents": 3}, "moins de 4"),
        (
            {"delta": 0.004, "bas": 0.001, "haut": 0.08, "desaccord_entre_executions": 0.01},
            "inférieur au désaccord",
        ),
        ({"desaccord_entre_executions": None}, "non mesurable"),
        ({"delta": -0.02, "bas": -0.05, "haut": -0.01}, "ne fait pas mieux"),
    ],
)
@pytest.mark.parametrize("pf", ["risk_averse", "risk_neutral"])
@pytest.mark.parametrize("contre", ["ET", "valuation_seul", "fundamental_seul"])
def test_chaque_condition_seule_suffit_a_rendre_non_concluant_sur_n_importe_quel_profil(
    modif, mot, pf, contre
):
    v = rp.calculer_verdict(_res({(pf, contre): modif}), CFG)
    assert v.statut == "non_concluant" and any(mot in r and f"[{pf}]" in r for r in v.raisons)
    # l'autre profil reste « conditions réunies »
    autre = "risk_neutral" if pf == "risk_averse" else "risk_averse"
    assert v.par_profil[autre]["conditions_reunies"] is True


def test_seuil_des_4_titres_borne_exacte_et_valeur_config():
    assert CFG.regles_rapport.min_titres_differents == 4
    assert (
        rp.calculer_verdict(_res({("risk_averse", "ET"): {"titres_differents": 4}}), CFG).statut
        == "multi_agent_meilleur"
    )
    assert (
        rp.calculer_verdict(_res({("risk_averse", "ET"): {"titres_differents": 3}}), CFG).statut
        == "non_concluant"
    )


def test_ecart_egal_au_desaccord_n_est_pas_inferieur_borne():
    v = rp.calculer_verdict(
        _res({("risk_averse", "ET"): {"delta": 0.01, "desaccord_entre_executions": 0.01}}), CFG
    )
    assert v.statut == "multi_agent_meilleur"  # « inférieur à » strict


def test_ou_et_ref15_ne_comptent_pas_dans_le_verdict_et_seul_baseline_est_lu():
    mauvais = {
        ("risk_averse", "OU"): {
            "bas": -1,
            "contient_zero": True,
            "delta": -1,
            "titres_differents": 0,
        },
        ("risk_neutral", "ref15"): {
            "bas": -1,
            "contient_zero": True,
            "delta": -1,
            "titres_differents": 0,
        },
    }
    assert (
        rp.calculer_verdict(_res(mauvais), CFG).statut == "multi_agent_meilleur"
    )  # choix du code : OU et ref15 décrits sans verdict
    res = _res()
    res["executions"]["t07_1"] = {"risk_averse": {"comparaisons": [_c("ET", bas=-1, delta=-1)]}}
    assert (
        rp.calculer_verdict(res, CFG).statut == "multi_agent_meilleur"
    )  # les autres exécutions ne servent qu'au désaccord


def test_limite_documentee_desaccord_nul_rend_la_condition_vide_cas_du_mock():
    """LIMITE : si le désaccord entre exécutions vaut exactement 0 (LLM simulé déterministe, ou 8
    exécutions identiques), `abs(delta) < 0` est toujours faux : la condition du plancher de bruit
    est vide. Elle ne protège que lorsque les exécutions diffèrent réellement."""
    v = rp.calculer_verdict(
        _res(
            {
                ("risk_averse", "ET"): {
                    "delta": 1e-9,
                    "bas": 1e-10,
                    "haut": 1e-8,
                    "desaccord_entre_executions": 0.0,
                }
            }
        ),
        CFG,
    )
    assert v.statut == "multi_agent_meilleur"


# ============================================================ fréquence de « meilleur » sur du bruit pur
def _frequence_meilleur(n_jeux, n_rep):
    """Simulation (12 jeux dans la suite ; 200 jeux lancés pendant la revue : 0/200 dans trois régimes
    de corrélation entre exécutions) : décisions tirées au hasard, indépendantes des prix."""
    import numpy as np
    import pandas as pd

    from amundi_agentic.evaluation import analyse
    from amundi_agentic.evaluation.tirage import Tirage

    cfg = charger_config(
        overrides={
            "tirage": {"n_titres": 14, "n_tirages_secondaires": 0},
            "inference": {"bootstrap": {"n_reechantillonnages": n_rep}},
        }
    )
    tit = ["ZS"] + [f"T{i:02d}" for i in range(14)]
    idx = pd.bdate_range("2024-02-01", "2024-05-31")
    execs = [e.nom for e in cfg.executions]
    meilleur = 0
    for s in range(n_jeux):
        rng = np.random.default_rng(500 + s)
        r = rng.normal(0.0004, 0.015, (len(idx), len(tit)))
        r[0] = 0
        prix = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=tit)

        class Src:
            synthetique = True

            def prix_suivi(self, titres, cfg_, prix=prix):
                return prix[list(titres)]

            def taux_suivi(self, cfg_):
                return pd.Series(5.3, index=pd.bdate_range("2024-01-02", "2024-05-31"))

        def debat(rng=rng):
            v, f = int(rng.integers(-1, 2)), int(rng.integers(-1, 2))
            return {
                "statut_debat": "ok",
                "votes_tour0": {"valuation": v, "fundamental": f},
                "final": {
                    "niveau": int(np.sign(v + f)),
                    "statut": "consensus",
                    "confiance": 0.5,
                    "tours": 1,
                    "plafonnee_par": None,
                },
                "sans_decision": None,
                "votants": [],
                "rejets": [],
                "prompts_sha256": {},
                "modeles_servis": [],
                "appels_reels": 0,
                "cache_hits": 0,
                "par_fournisseur": {},
                "tokens_entree": 0,
                "tokens_sortie": 0,
                "duree_s": 0.0,
            }

        debats = {f"{ex}|{pf}|{t}": debat() for ex in execs for pf in cfg.profils for t in tit}
        res = analyse.analyser(
            cfg, Src(), debats, {}, Tirage(tuple(tit[1:]), tuple(tit), tuple(tit[1:])), tit, execs
        )
        meilleur += rp.calculer_verdict(res, cfg).statut == "multi_agent_meilleur"
    return meilleur


def test_meilleur_sur_bruit_pur_rapide():
    assert _frequence_meilleur(6, 200) == 0


@pytest.mark.slow
def test_meilleur_sur_bruit_pur_40_jeux():
    assert _frequence_meilleur(40, 400) <= 1  # attendu 0 ; 0/200 mesuré pendant la revue


# ============================================================ formulations interdites
DETECTEES = [
    "MULTI-AGENT BAT LES AGENTS SEULS",
    "le multi-agent bat les agents seuls",
    "les multi-agents battent",
    "Robuste",
    "résultats robustes",
    "robustesse",
    "un résultat validé",
    "résultats validés",
    "valide la réplication",
    "alpha",
    "un Alpha",
    "alphas",
    "ALPHA",
    "génère de l'alpha",
    "confirme AlphaAgents",
    "confirms AlphaAgents",
    "confirme les résultats d'AlphaAgents",
    "conforme ESG",
    "Conforme esg",
    "analyse fondamentale",
    "Analyse Fondamentale",
    "surperformance",
    "sur-performance",
    "surperforme",
    "probabilité de succès",
    "confiance calibrée",
    "prouve la qualité du raisonnement",
    "le débat réduit la pensée de groupe",
    "hors échantillon",
    "bat\nles agents seuls",
]
NON_DETECTEES_LIMITE = [  # variantes qui PASSENT le balayage : limites documentées (rapport généré par gabarit)
    "le multi‑agent bat",
    "validated",
    "robust",
    "outperformance",
    "outperforms the single agents",
    "ESG-compliant",
    "fundamental analysis",
    "analyses fondamentales",
    "hors-échantillon",
    "out-of-sample",
    "sur performance",
    "la confiance est calibrée",
    "calibrated confidence",
    "le multi-agent l'emporte sur les agents seuls",
    "le multi-agent est meilleur que les agents seuls",
    "confirme les résultats du papier",
    "réduit les biais de groupe",
]


@pytest.mark.parametrize("texte", DETECTEES)
def test_formulation_interdite_detectee_casse_accents_pluriels(texte):
    assert rp.formulations_interdites(texte), texte


NOUVELLES_VARIANTES = [
    "Le MULTI AGENT BAT les agents seuls",
    "multi\u2010agent bat",
    "multi\u2013agent   bat",
    "multi\u00a0agent bat",
    "the multi-agent beats single agents",
    "multi-agent outperformed",
    "Outperformance du multi-agent",
    "A ROBUST result",
    "robustness",
    "résultats validés",
    "has been validated",
    "un Alpha net",
    "génère de l\u2019alpha",
    "ESG compliant",
    "ESG\u2011compliant",
    "analyse FONDAMENTALE",
    "fundamental analyses",
    "Out\u2011of\u2011Sample",
    "hors\u2011échantillon",
    "Hors   Echantillon",
    "calibrated confidence",
    "confiance CALIBRÉE",
    "success probability",
    "probabilité de réussite",
    "group-think reduced",
    "réduit les biais de groupe",
    "surperformance nette",
]


@pytest.mark.parametrize("texte", NON_DETECTEES_LIMITE + NOUVELLES_VARIANTES)
def test_variantes_precedemment_non_detectees_et_nouvelles_variantes_adverses_detectees(texte):
    assert rp.formulations_interdites(texte), texte


@pytest.mark.parametrize(
    "texte",
    [
        "Verdict : non concluant. L'intervalle de la différence contient 0.",
        "AlphaAgents est le papier de référence ; réplication qualitative.",
        "lecture qualitative de dépôts par un LLM",
        "alphabet, alphanumérique, validité du fichier, valider la config n'est pas interdit hors du mot validé",
        "Le multi-agent est plus conservateur à deux votants.",
        "robot de collecte",
        "bateau",
        "battement",
        "alphabétique",
    ],
)
def test_pas_de_faux_positif_sur_du_texte_legitime(texte):
    assert not rp.formulations_interdites(texte), texte


def test_la_liste_des_motifs_est_lue_dans_la_config_et_non_codee_dans_le_module(monkeypatch):
    assert len(CFG.rapport_interdit.motifs) >= 20
    assert rp.formulations_interdites("un résultat robuste")
    vide = charger_config(overrides={"rapport_interdit": {"motifs": ["zzzjamaisecrit"]}})
    monkeypatch.setattr(rp, "charger_config", lambda *a, **k: vide)
    rp._regles.cache_clear()
    try:
        assert (
            rp.formulations_interdites("un résultat robuste") == []
        )  # la liste vient de la config
        assert rp.formulations_interdites("zzzjamaisecrit")
    finally:
        monkeypatch.undo()
        rp._regles.cache_clear()
    assert rp.formulations_interdites("un résultat robuste")


def test_hors_echantillon_autorise_seulement_dans_la_formule_exacte():
    ok = "hors échantillon sous réserve d'un sondage de mémoire"
    assert not rp.formulations_interdites(ok) and not rp.formulations_interdites(ok.upper())
    assert rp.formulations_interdites("résultat hors échantillon pour Gemini")
    assert rp.formulations_interdites(ok + ", donc hors échantillon")


def test_rapport_interdit_leve_avant_ecriture_pour_formulation_et_pour_sharpe_sans_intervalle():
    bon = "| P | Sharpe [IC 95 %] |\n| --- | --- |\n| A | 0.50 [-1.00 ; 2.00] |\n| B | n/d |\n"
    assert rp.controler_sharpe_tableaux(bon) == []
    for mauvais in (
        "| P | Sharpe |\n| --- | --- |\n| A | 0.50 |\n",
        "| P | Sharpe [IC] |\n| --- | --- |\n| A | 1.2 |\n",
        "| P | Sharpe |\n| --- | --- |\n| A | 0.50 [1.0] |\n",
    ):
        assert rp.controler_sharpe_tableaux(mauvais), mauvais
    assert rp.fmt_sharpe(0.5, None) == "n/d" and rp.fmt_sharpe(None, [0, 1]) == "n/d"
    assert rp.fmt_sharpe(0.5, [-1.0, 2.0]) == "0.50 [-1.00 ; 2.00]"


# ============================================================ étiquettes de modèle (training_cutoff réel)
@pytest.mark.parametrize(
    "servi,attendu",
    [
        ("ollama/llama3.1:8b", CFG.modele.etiquette_marge),
        ("llama3.1:8b", CFG.modele.etiquette_marge),
        ("ollama_chat/llama3.1:8b", CFG.modele.etiquette_marge),
        ("gemini/gemini-3.8-flash", CFG.modele.etiquette_contamine),
        ("gemini/gemini-3.5-flash-lite", CFG.modele.etiquette_contamine),
        ("groq/openai/gpt-oss-120b", CFG.modele.etiquette_contamine),
        ("fournisseur/modele-inconnu", CFG.modele.etiquette_inconnue),
    ],
)
def test_etiquette_lue_dans_le_vrai_training_cutoff_prefixe_ou_non(servi, attendu):
    cut = load_config().training_cutoff
    assert "llama3.1:8b" in cut  # l'entrée existe dans config/llm.yaml : pas de défaut de clé
    assert dict(rp.etiquette_modele([servi], cut, CFG, simule=False))[servi] == attendu


def test_etiquette_apres_la_marge_hors_echantillon_sous_reserve_avec_une_decision_plus_tardive():
    """Même modèle (fin d'entraînement 2023-12-31), décision au-delà de la marge de 3 mois."""
    cfg_tard = charger_config(
        overrides={
            "cible": {
                "date_decision": "2024-06-03",
                "fin_suivi": "2024-09-30",
                "as_of_performance": "2024-10-01",
            }
        }
    )
    cut = load_config().training_cutoff
    assert (
        dict(rp.etiquette_modele(["ollama/llama3.1:8b"], cut, cfg_tard, simule=False))[
            "ollama/llama3.1:8b"
        ]
        == CFG.modele.etiquette_hors_echantillon
    )


@pytest.mark.parametrize(
    "fin_entrainement,attendu",
    [
        (
            date(2024, 2, 1),
            CFG.modele.etiquette_contamine,
        ),  # fin d'entraînement = décision : contaminé
        (date(2025, 6, 30), CFG.modele.etiquette_contamine),  # après la décision : contaminé
        (date(2024, 1, 31), CFG.modele.etiquette_marge),  # juste avant la décision : dans la marge
        (
            date(2023, 12, 31),
            CFG.modele.etiquette_marge,
        ),  # 2023-12-31 + 3 mois = 2024-03-31 >= décision
        (date(2023, 11, 1), CFG.modele.etiquette_marge),  # +3 mois = 2024-02-01 : borne incluse
        (
            date(2023, 10, 31),
            CFG.modele.etiquette_hors_echantillon,
        ),  # +3 mois = 2024-01-31 < décision
        (date(2023, 6, 30), CFG.modele.etiquette_hors_echantillon),
    ],
)
def test_marge_de_contamination_trois_zones_et_bornes(fin_entrainement, attendu):
    assert CFG.modele.marge_contamination_mois == 3 and CFG.cible.date_decision == date(2024, 2, 1)
    assert (
        dict(rp.etiquette_modele(["x/m"], {"m": fin_entrainement}, CFG, simule=False))["x/m"]
        == attendu
    )


def test_formules_d_etiquette_non_signalees_comme_formulation_interdite():
    for e in (CFG.modele.etiquette_hors_echantillon, CFG.modele.etiquette_marge):
        assert rp.formulations_interdites(e) == [] and rp.formulations_interdites(e.upper()) == []


# ============================================================ run simulé : bandeau, reproductibilité, écritures
def _args(out, **kw):
    base = dict(
        plan=False,
        run=True,
        mock=True,
        mock_llm=False,
        synthetic_data=False,
        llm_profile=None,
        mode="interactif",
        llm_config=None,
        executions="baseline,t07_1",
        univers="primaire",
        out=str(out),
        reprendre=None,
        max_debats=None,
        secondes_par_appel=None,
        prereg_racine=str(out / "pr"),
        n_pool_synth=20,
    )
    base.update(kw)
    return Namespace(**base)


@pytest.fixture(scope="module")
def run_mock(tmp_path_factory):
    d = tmp_path_factory.mktemp("mock")
    assert commande.executer_replicate(_args(d / "a")) == 0
    ra = next((d / "a").glob("*/"))
    return d, ra, None


@pytest.mark.slow
def test_deux_runs_mock_identiques_donnent_des_sorties_identiques_hors_horodatage(
    run_mock, tmp_path
):
    """Second run complet (environ 8 s) : marqué `slow` (`uv run pytest -m slow`)."""
    _, ra, _ = run_mock
    assert commande.executer_replicate(_args(tmp_path / "b")) == 0
    rb = next((tmp_path / "b").glob("*/"))
    for nom in (
        "rapport.md",
        "tableau_performance.csv",
        "tableau_decisions.csv",
        "tableau_comparaisons.csv",
        "tableau_kappa.csv",
        "journal_qualite.csv",
        "sharpe_glissant.csv",
    ):
        assert (ra / nom).read_bytes() == (rb / nom).read_bytes(), nom
    ja, jb = (
        json.loads((ra / "resultats.json").read_text()),
        json.loads((rb / "resultats.json").read_text()),
    )
    assert ja == jb


def test_rapport_mock_contient_avertissement_verdict_en_tete_et_pas_de_formulation_interdite(
    run_mock,
):
    texte = (run_mock[1] / "rapport.md").read_text(encoding="utf-8")
    pos_titre = texte.index("# Réplication AlphaAgents")
    pos_avert = texte.index("> Prototype académique")
    pos_bandeau = texte.index("ESSAI DE MÉCANIQUE")
    pos_verdict = texte.index("## Verdict")
    # ordre : titre, avertissement, bandeau d'essai, verdict ; le tout avant toute autre section
    assert pos_titre < pos_avert < pos_bandeau < pos_verdict
    assert pos_verdict < texte.index("## Modèle et étiquette")
    assert "conseil en investissement" in texte[pos_avert:pos_bandeau]
    assert rp.formulations_interdites(texte) == [] and rp.controler_sharpe_tableaux(texte) == []
    assert "sharpe_glissant.csv" in texte and "n'a pas d'intervalle" in texte
    assert "(simulé)" in texte and rp.etiquette_modele([], {}, CFG, simule=True)[0][1] in texte


def test_rapport_mock_a_un_bandeau_obligatoire_en_tete_et_dit_kappa_et_desaccord(run_mock):
    entete = "\n".join(
        (run_mock[1] / "rapport.md").read_text(encoding="utf-8").splitlines()[:12]
    ).lower()
    assert "simul" in entete and "kappa" in entete


def test_rien_n_est_ecrit_hors_du_dossier_de_sortie_ni_dans_runs(run_mock):
    d, _, _ = run_mock
    assert sorted(p.name for p in (d / "a").iterdir()) == [next((d / "a").glob("*/")).name]
    for nom in ("rapport.md", "resultats.json", "execution.json", "etat.json"):
        assert (next((d / "a").glob("*/")) / nom).exists()
    assert not (ROOT / "runs" / "replication").exists() or not any(
        (ROOT / "runs" / "replication").glob("2026*")
    )


def test_plan_n_appelle_aucun_llm_et_ne_cree_aucun_fichier(tmp_path, monkeypatch, capsys):
    def interdit(*a, **k):
        raise AssertionError("client LLM construit par --plan")

    monkeypatch.setattr(commande, "LLMClient", interdit)
    monkeypatch.setattr(commande, "MockLLMClient", interdit)
    a = _args(tmp_path, plan=True, run=False, executions=None, mock=True, univers="pool")
    avant = sorted(p for p in tmp_path.rglob("*"))
    assert commande.executer_replicate(a) == 0
    assert sorted(p for p in tmp_path.rglob("*")) == avant == []
    sortie = capsys.readouterr().out
    assert "aucun appel n'est fait par --plan" in sortie and "durée : non estimée" in sortie


def test_cout_en_appels_recalcule_et_secondes_par_appel_non_inventees():
    s = load_settings()
    n_votants = len(CFG.evaluation.agents_votants)
    mini, maxi = n_votants + 1, n_votants + 1 + n_votants * s.debate.r_max + 1
    assert (mini, maxi) == (3, 8) and s.debate.r_max == 2
    n_debats = 63 * len(CFG.profils) * len(CFG.executions)
    assert n_debats == 1008 and (n_debats * mini, n_debats * maxi) == (3024, 8064)
    assert CFG.cout.secondes_par_appel is None  # jamais inventée
    from amundi_agentic.evaluation.replication import appels_par_debat

    assert appels_par_debat(s, n_votants) == (3, 8)


def _code_sans_docstrings(f):
    import ast

    arbre = ast.parse(f.read_text(encoding="utf-8"))
    docs = set()
    for n in ast.walk(arbre):
        corps = getattr(n, "body", None)
        if (
            isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef)
            and corps
            and isinstance(corps[0], ast.Expr)
            and isinstance(corps[0].value, ast.Constant)
        ):
            docs.add(id(corps[0].value))
    return [
        n.value
        for n in ast.walk(arbre)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    ]


def test_aucun_nom_de_modele_ni_cle_dans_le_code_du_harnais_et_la_config():
    interdits = re.compile(
        r"gemini|llama|gpt-|claude|groq|ollama|mistral|qwen|nomic", re.IGNORECASE
    )
    cles = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}")
    for nom in (
        "repl_config",
        "tirage",
        "preregistration",
        "sources",
        "portefeuilles",
        "perf",
        "inference",
        "replication",
        "analyse",
        "rapport",
        "commande",
    ):
        f = ROOT / "src" / "amundi_agentic" / "evaluation" / f"{nom}.py"
        for morceau in _code_sans_docstrings(f):
            assert not interdits.search(morceau), (nom, morceau[:60])
        assert not cles.search(f.read_text(encoding="utf-8")), nom
    yaml_txt = (ROOT / "config" / "replication.yaml").read_text(encoding="utf-8")
    valeurs = "\n".join(
        re.sub(r"#.*", "", ligne) for ligne in yaml_txt.splitlines()
    )  # commentaires exclus
    assert not cles.search(yaml_txt) and not interdits.search(valeurs)


def test_variables_d_environnement_des_donnees_documentees_et_distinguees():
    docs = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [
            ROOT / "README.md",
            ROOT / "config" / "README.md",
            ROOT / ".env.example",
            *(ROOT / "docs").glob("*.md"),
        ]
        if p.exists()
    )
    assert "AMUNDI_DATA_DIR" in docs and "AMUNDI_RAG_DIR" in docs


_ = (subprocess, date)


def test_comparaison_avec_le_papier_qualitative_aucun_chiffre_du_papier(run_mock):
    texte = (run_mock[1] / "rapport.md").read_text(encoding="utf-8")
    bloc = texte.split("## Comparaison qualitative avec le papier")[1].split("## Limites")[0]
    lignes = [x for x in bloc.splitlines() if x.startswith("|") and not set(x) <= set("|- ")][1:]
    assert lignes, "tableau qualitatif absent"
    for ligne in lignes:
        col_papier, col_observe, col_lecture = (c.strip() for c in ligne.strip("|").split("|"))
        assert not re.search(r"\d", col_papier), col_papier  # aucune valeur attribuée au papier
        assert col_lecture in {"cohérent", "différent", "indéterminé"}
    assert "aucun chiffre du papier" in texte.lower()


def _res_meta(run_mock):
    contenu = json.loads((run_mock[1] / "resultats.json").read_text(encoding="utf-8"))
    res = contenu["resultats"]
    meta = {**contenu["meta"], "qualitatif": [tuple(x) for x in contenu["qualitatif"]]}
    meta["etiquettes"] = [tuple(x) for x in meta["etiquettes"]]
    v = rp.calculer_verdict(res, CFG)
    return res, v, meta


def test_rendre_rapport_refuse_d_ecrire_un_texte_avec_formulation_interdite(run_mock):
    res, v, meta = _res_meta(run_mock)
    assert rp.rendre_rapport(CFG, res, v, meta)  # le rapport normal passe
    for piege in (
        "un résultat robuste",
        "le multi-agent bat les agents seuls",
        "un alpha positif",
        "résultat hors échantillon pour Gemini",
    ):
        meta2 = {**meta, "qualitatif": [*meta["qualitatif"], (piege, "x", "cohérent")]}
        with pytest.raises(rp.RapportInterdit):
            rp.rendre_rapport(CFG, res, v, meta2)
