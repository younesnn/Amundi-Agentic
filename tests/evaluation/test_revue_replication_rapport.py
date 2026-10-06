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
def test_meilleur_sur_decisions_aleatoires_independantes_du_marche_est_tres_rare():
    """Simulation (30 jeux dans la suite ; 200 jeux lancés pendant la revue : 0/200 dans trois régimes
    de corrélation entre exécutions) : décisions tirées au hasard, indépendantes des prix."""
    import numpy as np
    import pandas as pd

    from amundi_agentic.evaluation import analyse
    from amundi_agentic.evaluation.tirage import Tirage

    cfg = charger_config(
        overrides={
            "tirage": {"n_titres": 14, "n_tirages_secondaires": 0},
            "inference": {"bootstrap": {"n_reechantillonnages": 300}},
        }
    )
    tit = ["ZS"] + [f"T{i:02d}" for i in range(14)]
    idx = pd.bdate_range("2024-02-01", "2024-05-31")
    execs = [e.nom for e in cfg.executions]
    meilleur = 0
    for s in range(30):
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
    assert meilleur <= 1  # attendu 0 ; 0/200 mesuré pendant la revue


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


def test_limite_variantes_non_detectees_liste_explicite_a_completer():
    """LIMITE (non bloquante) : balayage par expressions régulières françaises ; des variantes
    anglaises, des traits d'union insécables et des paraphrases passent. Le texte du rapport étant
    produit par un gabarit sans texte libre de LLM, le risque est faible ; si un jour une variante
    est ajoutée à `FORMULATIONS_INTERDITES`, mettre à jour cette liste."""
    passent = [t for t in NON_DETECTEES_LIMITE if not rp.formulations_interdites(t)]
    assert passent == NON_DETECTEES_LIMITE


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
        ("ollama/llama3.1:8b", CFG.modele.etiquette_hors_echantillon),
        ("llama3.1:8b", CFG.modele.etiquette_hors_echantillon),
        ("ollama_chat/llama3.1:8b", CFG.modele.etiquette_hors_echantillon),
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


def test_marge_de_contamination_de_la_config_n_est_lue_par_aucun_code_limite():
    """LIMITE (non bloquante) : `modele.marge_contamination_mois` (3) est validée mais jamais
    utilisée : l'étiquette ne dépend que de `cut >= date_decision`. Avec la marge, llama3.1:8b
    (2023-12-31 + 3 mois = 2024-03-31) serait « contaminé » à la date de décision."""
    src = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "src" / "amundi_agentic" / "evaluation").glob("*.py")
    )
    assert src.count("marge_contamination") == 1  # seule la déclaration du champ


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
    assert commande.executer_replicate(_args(d / "b")) == 0
    ra = next((d / "a").glob("*/"))
    rb = next((d / "b").glob("*/"))
    return d, ra, rb


def test_deux_runs_mock_identiques_donnent_des_sorties_identiques_hors_horodatage(run_mock):
    _, ra, rb = run_mock
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
    lignes = texte.splitlines()
    assert (
        lignes[2].startswith("> Prototype académique") and "conseil en investissement" in lignes[2]
    )
    assert lignes[4].startswith("## Verdict")
    assert rp.formulations_interdites(texte) == [] and rp.controler_sharpe_tableaux(texte) == []
    assert (
        "sharpe_glissant.csv" in texte and "n'a pas d'intervalle" in texte
    )  # limite du Sharpe glissant signalée
    assert "(simulé)" in texte and rp.etiquette_modele([], {}, CFG, simule=True)[0][1] in texte


@pytest.mark.xfail(
    strict=True,
    reason="IMPORTANT (revue) : un rapport produit avec `--mock` n'a AUCUN bandeau en tête : le verdict "
    "(« NON CONCLUANT » ou « multi-agent meilleur ») s'affiche comme pour un résultat réel, seule la ligne "
    "« modèle servi (simulé) » plus bas le signale, et rien n'indique que kappa = 1 et le désaccord = 0 par "
    "construction. Correction : bandeau obligatoire en tête (« ESSAI DE MÉCANIQUE : LLM simulé ... »).",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="NON BLOQUANT (revue) : `AMUNDI_DATA_DIR` (couche de données) et `AMUNDI_RAG_DIR` (sources.py) ne "
    "sont expliquées ni dans README.md, config/README.md, docs/ ni .env.example (seulement dans un commentaire "
    "de config/data.yaml). `AMUNDI_DATA_STORE` n'existe que pour les tests de revue (dossier store/ lui-même, "
    "alors que `AMUNDI_DATA_DIR` désigne son parent contenant store/ et snapshots/) : source de confusion.",
)
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
