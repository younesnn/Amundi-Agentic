# ruff: noqa: E501
"""Revue indépendante : pré-enregistrement en ajout seul, tirage primaire recalculé, règle de remplacement.

Aucun réseau, aucune clé, aucun appel LLM. Le tirage est recalculé avec hashlib seulement.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest

from amundi_agentic.data.settings import CONFIG_DIR, ROOT
from amundi_agentic.evaluation import commande
from amundi_agentic.evaluation import preregistration as pr
from amundi_agentic.evaluation import replication as rep
from amundi_agentic.evaluation import tirage as tr
from amundi_agentic.evaluation.repl_config import charger_config

ANNONCE = [
    "TRMB",
    "AMAT",
    "NVDA",
    "CTSH",
    "NTAP",
    "CRM",
    "IT",
    "QCOM",
    "IBM",
    "GEN",
    "PTC",
    "EPAM",
    "ADI",
    "KEYS",
]
SHA_GRAINE = "d7458cc2854316191485a831d14dbb2b9313ee4cdf2194c2d2995997834e88f5"


# ============================================================ tirage recalculé indépendamment
def _perm(pool, graine, etiquette="primaire"):
    return sorted(
        set(pool),
        key=lambda t: (hashlib.sha256(f"{graine}|{etiquette}|{t}".encode()).hexdigest(), t),
    )


def test_hash_de_graine_recalcule_et_valeur_annoncee():
    h = hashlib.sha256(b"amundi-agentic/replication/graine/v1|20240201").hexdigest()
    assert h == tr.graine_sha256(20240201) == SHA_GRAINE
    assert charger_config().tirage.graine == 20240201


def test_tirage_synthetique_egal_a_l_oracle_independant_de_l_ordre_et_du_dictionnaire():
    pool = [f"S{i:02d}" for i in range(62)]
    oracle = _perm(pool, 20240201)[:14]
    for ordre in (
        pool,
        pool[::-1],
        random.Random(1).sample(pool, 62),
        set(pool),
        dict.fromkeys(reversed(pool)),
    ):
        t = tr.tirage_primaire(list(ordre), hors_pool="ZS", n=14, graine=20240201)
        assert list(t.retenus) == oracle and t.titres == ("ZS", *oracle) and not t.insuffisant


def test_tirage_du_pool_reel_egal_a_l_annonce_si_le_stockage_est_disponible():
    magasin = os.environ.get("AMUNDI_DATA_STORE")
    if not magasin or not (Path(magasin) / "universe" / "pool.parquet").exists():
        pytest.skip(
            "variable AMUNDI_DATA_STORE absente : pool réel non lu (commande dans le rapport)"
        )
    import pandas as pd

    pool = list(pd.read_parquet(Path(magasin) / "universe" / "pool.parquet")["ticker"])
    utilisables = [t for t in pool if t not in ("ANSS", "JNPR")]  # sans prix dans le stockage
    assert len(pool) == 64 and len(utilisables) == 62 and "ZS" not in pool
    assert _perm(utilisables, 20240201)[:14] == ANNONCE
    assert (
        list(tr.tirage_primaire(utilisables, hors_pool="ZS", n=14, graine=20240201).retenus)
        == ANNONCE
    )


def test_tirage_ne_depend_ni_de_numpy_ni_du_module_random():
    import ast

    arbre = ast.parse(Path(tr.__file__).read_text(encoding="utf-8"))
    importes = {
        (n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
        for n in ast.walk(arbre)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [None])
        if (n.module if isinstance(n, ast.ImportFrom) else a.name)
    }
    assert importes <= {"__future__", "hashlib", "collections", "dataclasses"}, importes
    random.seed(1)
    a = tr.tirage_primaire([f"S{i}" for i in range(30)], hors_pool="ZS", n=5, graine=1).retenus
    random.seed(999)
    b = tr.tirage_primaire([f"S{i}" for i in range(30)], hors_pool="ZS", n=5, graine=1).retenus
    assert a == b


def test_graine_differente_ou_etiquette_differente_donnent_d_autres_tirages():
    pool = [f"S{i:02d}" for i in range(40)]
    assert tr.permutation(pool, 1) != tr.permutation(pool, 2)
    assert tr.permutation(pool, 1, "primaire") != tr.permutation(pool, 1, "secondaire|0")
    assert tr.permutation(pool, 1, "secondaire|0") != tr.permutation(pool, 1, "secondaire|1")


def test_verifier_graine_refuse_toute_autre_graine():
    tr.verifier_graine(20240201, SHA_GRAINE)
    for autre in (20240202, 0, -1, 2024020):
        with pytest.raises(tr.GraineNonConforme):
            tr.verifier_graine(autre, SHA_GRAINE)
    with pytest.raises(tr.GraineNonConforme):
        tr.verifier_graine(20240201, "0" * 64)


# ============================================================ remplacement : échec technique seulement
def _debat(statut, motif="", niveau=None, votes=None):
    return {
        "statut_debat": statut,
        "motif": motif,
        "votes_tour0": votes or {},
        "final": None if niveau is None else {"niveau": niveau, "statut": "consensus"},
    }


def test_remplacement_ne_depend_que_du_statut_technique_jamais_de_la_decision_ni_du_rendement():
    debats = {
        "baseline|risk_averse|A": _debat(
            "ok", niveau=-2, votes={"valuation": -2}
        ),  # SELL franc : jamais remplacé
        "baseline|risk_averse|B": _debat("ok", niveau=None),  # abstention : jamais remplacé
        "baseline|risk_averse|C": _debat("exclu_esg", "veto"),  # veto ESG : pas un échec technique
        "baseline|risk_averse|D": _debat("echec_donnees", "données indisponibles (KeyError)"),
        "t07_1|risk_averse|E": _debat(
            "echec_fournisseur", "panne passagère"
        ),  # hors baseline : ignoré
        "baseline|risk_averse|F": _debat("echec_fournisseur", "panne"),  # baseline : remplacé
        "t07_1|risk_neutral|G": _debat("echec_donnees", "x"),  # données : toute exécution
    }
    assert rep.echecs_techniques(debats) == {
        "D": "données indisponibles (KeyError)",
        "F": "panne",
        "G": "x",
    }


def test_remplacement_prend_le_titre_suivant_de_la_permutation_sans_regarder_autre_chose():
    pool = [f"S{i:02d}" for i in range(30)]
    perm = _perm(pool, 20240201)
    base = tr.tirage_primaire(pool, hors_pool="ZS", n=5, graine=20240201)
    assert list(base.retenus) == perm[:5]
    t = tr.tirage_primaire(
        pool, hors_pool="ZS", n=5, graine=20240201, echecs={perm[1]: "x", perm[3]: "y"}
    )
    assert list(t.retenus) == [perm[0], perm[2], perm[4], perm[5], perm[6]]
    assert t.remplaces == {perm[1]: perm[5], perm[3]: perm[6]}
    # le motif de l'échec n'influence pas le choix
    t2 = tr.tirage_primaire(
        pool,
        hors_pool="ZS",
        n=5,
        graine=20240201,
        echecs={perm[1]: "quoi que ce soit", perm[3]: ""},
    )
    assert t.retenus == t2.retenus
    # pool trop petit : « insuffisant », jamais un titre inventé
    petit = tr.tirage_primaire(pool[:3], hors_pool="ZS", n=5, graine=20240201)
    assert petit.insuffisant and len(petit.retenus) == 3


def test_tirages_secondaires_reproductibles_sans_hors_pool_et_independants_de_l_ordre():
    pool = [f"S{i:02d}" for i in range(30)]
    a = tr.tirages_secondaires(pool, hors_pool="S00", n=5, graine=7, nombre=20)
    b = tr.tirages_secondaires(pool[::-1], hors_pool="S00", n=5, graine=7, nombre=20)
    assert a == b and all("S00" not in x and len(set(x)) == 5 for x in a)
    assert len({x for x in a}) > 10  # tirages réellement différents


# ============================================================ pré-enregistrement : projet copié
@pytest.fixture
def projet(tmp_path):
    p = tmp_path / "projet"
    shutil.copytree(
        CONFIG_DIR, p / "config", ignore=shutil.ignore_patterns("esg_etf_sources_archive")
    )
    shutil.copytree(ROOT / "agent_prompts", p / "agent_prompts")
    shutil.copy(ROOT / "uv.lock", p / "uv.lock")
    return p


def _enr(projet, cfg=None, **kw):
    cfg = cfg or charger_config(projet / "config" / "replication.yaml")
    return pr.enregistrer(
        cfg,
        racine=projet / "pr",
        config_dir=projet / "config",
        prompts_dir=projet / "agent_prompts",
        racine_projet=projet,
        **kw,
    )


def _verif(projet, cfg=None):
    cfg = cfg or charger_config(projet / "config" / "replication.yaml")
    return pr.verifier(
        cfg,
        racine=projet / "pr",
        config_dir=projet / "config",
        prompts_dir=projet / "agent_prompts",
        racine_projet=projet,
    )


def _chemins(rv):
    return {e.chemin for e in rv.ecarts}


def test_conforme_puis_chaque_derive_est_detectee_avec_son_chemin(projet):
    _enr(projet)
    assert _verif(projet).ok
    cas = {
        "uv.lock": (projet / "uv.lock", "\n# modif\n", "uv_lock_sha256"),
        "paraphrase": (
            projet / "config" / "replication_paraphrases" / "paraphrase_1" / "devil_v1.md",
            "\nmodif\n",
            "prompts.paraphrases.paraphrase_1.devil_v1",
        ),
        "prompt de role": (
            projet / "agent_prompts" / "coordinator_report_v1.md",
            "\nmodif\n",
            "prompts.roles.coordinator_report",
        ),
        "esg": (projet / "config" / "esg.yaml", "\n# m\n", "configs.esg.yaml"),
        "universe": (projet / "config" / "universe.yaml", "\n# m\n", "configs.universe.yaml"),
        "text_tools": (projet / "config" / "text_tools.yaml", "\n# m\n", "configs.text_tools.yaml"),
    }
    for nom, (f, ajout, chemin) in cas.items():
        original = f.read_bytes()
        f.write_bytes(original + ajout.encode())
        rv = _verif(projet)
        assert not rv.ok and any(c.startswith(chemin) or c == chemin for c in _chemins(rv)), (
            nom,
            _chemins(rv),
        )
        f.write_bytes(original)
        assert _verif(projet).ok, nom  # revenir à l'état d'origine redonne « conforme »


def test_derive_de_la_graine_seule_et_de_chaque_parametre_du_protocole(projet):
    _enr(projet)
    y = projet / "config" / "replication.yaml"
    base = y.read_text(encoding="utf-8")
    for avant, apres, cle in (
        ("graine: 20240201", "graine: 20240299", "graine_sha256"),
        (
            "min_titres_differents: 4",
            "min_titres_differents: 2",
            "protocole.regles_rapport.min_titres_differents",
        ),
        (
            "longueur_moyenne_bloc: 5",
            "longueur_moyenne_bloc: 7",
            "protocole.inference.bootstrap.longueur_moyenne_bloc",
        ),
        (
            "buy_si_niveau_superieur_a: 0",
            "buy_si_niveau_superieur_a: -1",
            "protocole.mapping.buy_si_niveau_superieur_a",
        ),
        (
            "fenetre_sharpe_glissant: 21",
            "fenetre_sharpe_glissant: 42",
            "protocole.performance.fenetre_sharpe_glissant",
        ),
        ("fin_suivi: 2024-05-31", "fin_suivi: 2024-05-30", "protocole.cible.fin_suivi"),
    ):
        y.write_text(base.replace(avant, apres, 1), encoding="utf-8")
        assert avant in base
        rv = _verif(projet, charger_config(y))
        assert cle in _chemins(rv), (cle, _chemins(rv))
    y.write_text(base, encoding="utf-8")
    assert _verif(projet).ok


def test_commentaire_seul_dans_la_config_est_une_deviation_car_le_fichier_est_hashe_en_octets(
    projet,
):
    _enr(projet)
    y = projet / "config" / "replication.yaml"
    y.write_text(y.read_text(encoding="utf-8") + "\n# commentaire\n", encoding="utf-8")
    rv = _verif(projet)
    assert not rv.ok and _chemins(rv) == {"configs.replication.yaml"}  # aucun paramètre ne change


def test_creation_exclusive_jamais_d_ecrasement_et_chaine_alteree_refusee(projet):
    e1 = _enr(projet, aujourd_hui=date(2026, 1, 2))
    avant = e1.chemin.read_bytes()
    y = projet / "config" / "replication.yaml"
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 14", "n_titres: 13"), encoding="utf-8"
    )
    e2 = _enr(projet, motif="essai", aujourd_hui=date(2026, 1, 2))
    assert e2.chemin.name == "2026-01-02-2.json" and e1.chemin.read_bytes() == avant
    # même jour, même nom pré-créé par un tiers : `open('x')` interdit l'écrasement, on prend le suffixe suivant
    (projet / "pr" / "alphaagents_replication" / "2026-01-02-3.json").write_text("{}")
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 13", "n_titres: 12"), encoding="utf-8"
    )
    with pytest.raises(
        pr.PreenregistrementError
    ):  # fichier « {} » : chaîne altérée, nouvelle version refusée
        _enr(projet, motif="encore", aujourd_hui=date(2026, 1, 2))


def test_motif_obligatoire_et_motif_blanc_refuse(projet):
    _enr(projet)
    y = projet / "config" / "replication.yaml"
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 14", "n_titres: 13"), encoding="utf-8"
    )
    for motif in (None, "", "   "):
        with pytest.raises(pr.MotifRequis):
            _enr(projet, motif=motif)
    assert len(pr.lister("alphaagents_replication", projet / "pr")) == 1


def _deux_versions(projet):
    e1 = _enr(projet, aujourd_hui=date(2026, 1, 2))
    y = projet / "config" / "replication.yaml"
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 14", "n_titres: 13"), encoding="utf-8"
    )
    e2 = _enr(projet, motif="m", aujourd_hui=date(2026, 1, 3))
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 13", "n_titres: 12"), encoding="utf-8"
    )
    e3 = _enr(projet, motif="m2", aujourd_hui=date(2026, 1, 4))
    return e1, e2, e3


def test_chaine_detecte_alteration_suppression_au_milieu_et_reordonnancement(projet):
    nom = "alphaagents_replication"
    racine = projet / "pr"
    e1, e2, e3 = _deux_versions(projet)
    assert pr.verifier_chaine(nom, racine) == []
    # 1. altération de la version 2 : la version 3 ne la référence plus correctement
    contenu = e2.chemin.read_bytes()
    e2.chemin.write_bytes(contenu + b" ")
    assert any("modifiée" in p for p in pr.verifier_chaine(nom, racine))
    e2.chemin.write_bytes(contenu)
    assert pr.verifier_chaine(nom, racine) == []
    # 2. suppression de la version du milieu
    sauvegarde = e2.chemin.read_bytes()
    e2.chemin.unlink()
    assert pr.verifier_chaine(nom, racine)
    e2.chemin.write_bytes(sauvegarde)
    # 3. réordonnancement par renommage des dates
    e1.chemin.rename(e1.chemin.with_name("2026-01-09.json"))
    assert pr.verifier_chaine(nom, racine)


def test_limite_documentee_alteration_ou_suppression_de_la_derniere_version_non_vue_par_la_chaine(
    projet,
):
    """LIMITE (non bloquante) : la chaîne ne protège pas la DERNIÈRE version (aucune suivante ne la
    référence) ; la parade est Git (commit de `runs/preregistration/`) et `--verify <hash>` avec le
    hash relevé hors du dépôt. Supprimer la dernière version fait redevenir « dernier » la précédente."""
    nom = "alphaagents_replication"
    e1, e2, e3 = _deux_versions(projet)
    e3.chemin.write_bytes(e3.chemin.read_bytes().replace(b"12", b"99"))
    assert (
        pr.verifier_chaine(nom, projet / "pr") == []
    )  # altération de la dernière : non détectée par la chaîne
    e3.chemin.unlink()
    assert pr.lister(nom, projet / "pr")[-1] == e2.chemin  # la version 2 redevient la dernière
    rv = _verif(projet)  # et l'état courant (n_titres: 12) ne correspond plus à elle
    assert not rv.ok and "protocole.tirage.n_titres" in _chemins(rv)


def test_graine_enregistree_avant_tout_tirage_et_tirage_non_effectue(projet):
    e = _enr(projet)
    rec = json.loads(e.chemin.read_text(encoding="utf-8"))
    assert rec["tirage_effectue"] is False and rec["empreintes"]["graine_sha256"] == SHA_GRAINE
    # la graine figure aussi en clair dans le protocole recopié : le hash prouve l'absence de
    # changement, pas un secret (documenté)
    assert rec["empreintes"]["protocole"]["tirage"]["graine"] == 20240201
    assert rec["avertissement"].startswith("Prototype académique")


# ============================================================ refus d'un run réel
def _args(tmp_path, **kw):
    base = dict(
        plan=False,
        run=True,
        mock=False,
        mock_llm=False,
        synthetic_data=True,
        llm_profile="dev",
        mode="interactif",
        llm_config=None,
        executions="baseline",
        univers="primaire",
        out=str(tmp_path),
        reprendre=None,
        max_debats=None,
        secondes_par_appel=None,
        prereg_racine=str(tmp_path / "pr"),
        n_pool_synth=20,
    )
    base.update(kw)
    return Namespace(**base)


def _sans_llm_reel(monkeypatch):
    """Garde-fou de la revue : aucun client LLM réel (donc aucun appel Ollama) ne peut être construit."""

    def interdit(*a, **k):
        raise AssertionError("client LLM réel construit : un run réel aurait été lancé")

    monkeypatch.setattr(commande, "LLMClient", interdit)


def test_run_reel_refuse_sans_enregistrement_ou_avec_deviation_ou_en_evaluation_sans_prod(
    tmp_path, capsys, monkeypatch
):
    _sans_llm_reel(monkeypatch)
    assert commande.executer_replicate(_args(tmp_path)) == 2
    assert "pré-enregistrement" in capsys.readouterr().err
    pr.enregistrer(charger_config(), racine=tmp_path / "pr", manifeste=None)
    # protocole dévié dans une copie du fichier (le hash est celui du FICHIER lu) : refus
    copie = tmp_path / "replication_devie.yaml"
    copie.write_text(
        (CONFIG_DIR / "replication.yaml")
        .read_text(encoding="utf-8")
        .replace("n_titres: 14", "n_titres: 13"),
        encoding="utf-8",
    )
    vrai = commande.charger_config
    monkeypatch.setattr(commande, "charger_config", lambda *a, **k: vrai(copie))
    assert commande.executer_replicate(_args(tmp_path)) == 2
    assert "refusée" in capsys.readouterr().err
    monkeypatch.setattr(commande, "charger_config", vrai)
    assert commande.executer_replicate(_args(tmp_path, mode="evaluation")) == 2
    assert "prod" in capsys.readouterr().err
    assert [p.name for p in tmp_path.iterdir()] == [
        "pr",
        "replication_devie.yaml",
    ]  # aucun run créé


def test_execution_baseline_exigee_et_executions_inconnues_refusees(tmp_path, capsys, monkeypatch):
    _sans_llm_reel(monkeypatch)
    assert commande.executer_replicate(_args(tmp_path, executions="t07_1", mock=True)) == 2
    assert (
        commande.executer_replicate(_args(tmp_path, executions="baseline,nexiste_pas", mock=True))
        == 2
    )
    assert [p.name for p in tmp_path.iterdir()] == []
