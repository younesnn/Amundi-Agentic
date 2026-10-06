# ruff: noqa: E501
"""Réplication de bout en bout avec LLM simulé et données synthétiques (aucun réseau, aucune clé)."""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import date

import pandas as pd
import pytest

from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.data.models import LookAheadError
from amundi_agentic.evaluation import analyse, commande, rapport
from amundi_agentic.evaluation import perf as perf_mod
from amundi_agentic.evaluation.repl_config import charger_config
from amundi_agentic.evaluation.replication import (
    Etat,
    ReplicationInterrompue,
    produire_decisions,
)
from amundi_agentic.evaluation.sources import GardeFuture, SourceSynthetique, etat_pool
from amundi_agentic.llm import MockLLMClient, load_config

SURCHARGE = {
    "tirage": {"n_titres": 4, "n_tirages_secondaires": 30},
    "inference": {"bootstrap": {"n_reechantillonnages": 200}},
    "executions": [
        {"nom": "baseline", "temperature": 0.0, "paraphrase": None, "graine_llm": 0},
        {"nom": "paraphrase_1", "temperature": 0.0, "paraphrase": "paraphrase_1", "graine_llm": 0},
        {"nom": "t07_1", "temperature": 0.7, "paraphrase": None, "graine_llm": 1},
    ],
}


def _monde(tmp_path, n_pool=9):
    cfg = charger_config(overrides=SURCHARGE)
    src = SourceSynthetique(cfg, n_pool=n_pool, sans_donnees=2)
    ep = etat_pool(src, cfg)
    llm_cfg = load_config()
    seen: list = []

    def fab(ex, *, cache_dir):
        conf = llm_cfg.model_copy(
            update={"defaults": llm_cfg.defaults.model_copy(update={"temperature": ex.temperature})}
        )
        c = MockLLMClient(
            conf,
            handler=politique_simulee,
            mode="interactif",
            run_id=f"replication-{ex.nom}",
            seed=ex.graine_llm,
        )
        seen.append((ex.nom, c))
        return c

    return cfg, src, ep, load_settings(), fab, seen


def _tout(tmp_path, nom="a", **kw):
    cfg, src, ep, settings, fab, seen = _monde(tmp_path)
    etat = Etat(tmp_path / nom / "etat.json", cfg.source_sha256 or "")
    (tmp_path / nom).mkdir(exist_ok=True)
    execs = [e.nom for e in cfg.executions]
    dec = produire_decisions(
        cfg,
        src,
        ep,
        settings,
        etat,
        fab,
        executions=execs,
        univers="pool",
        dossier_cache=None,
        **kw,
    )
    return cfg, src, ep, etat, dec, execs, seen


@pytest.fixture(scope="module")
def run_ref(tmp_path_factory):
    return _tout(tmp_path_factory.mktemp("ref"), "ref")


def _rapport(cfg, src, ep, etat, dec, execs):
    res = analyse.analyser(
        cfg, src, etat.debats, etat.donnees["caracteristiques"], dec.tirage, dec.evalues, execs
    )
    v = rapport.calculer_verdict(res, cfg)
    meta = {
        "etiquettes": rapport.etiquette_modele([], {}, cfg, simule=True),
        "preenregistrement": {"statut": "absent", "sha256": None},
        "graine_sha256": "x",
        "graine_verifiee": False,
        "n_pool": len(ep.pool),
        "n_utilisables": len(ep.utilisables),
        "exclus": ep.exclus,
        "remplaces": dec.tirage.remplaces,
        "executions": execs,
        "modeles_servis": etat.donnees["modeles_servis"],
        "qualitatif": commande.observations_qualitatives(res, cfg),
    }
    return res, v, rapport.rendre_rapport(cfg, res, v, meta)


def test_pool_exclut_les_titres_sans_donnees_et_ajoute_zs(tmp_path):
    cfg, src, ep, *_ = _monde(tmp_path)
    assert set(ep.exclus) == {"SYN08", "SYN09"} and "ZS" not in ep.pool
    assert all("aucune donnée" in m for m in ep.exclus.values())


def test_un_debat_par_titre_profil_et_execution_sans_sentiment(run_ref):
    cfg, src, ep, etat, dec, execs, seen = run_ref
    titres = sorted({*ep.utilisables, "ZS"})
    assert len(etat.debats) == len(titres) * 2 * 3
    for d in etat.debats.values():
        assert d["statut_debat"] == "ok"
        assert (
            not any("sentiment" in a for a in d["votes_tour0"]) and "sentiment" not in d["votants"]
        )
        assert set(d["votes_tour0"]) <= {"valuation", "fundamental"}
    assert len(dec.tirage.titres) == 5 and dec.tirage.titres[0] == "ZS"


def test_rapport_complet_et_verdict_calcule_en_tete(run_ref):
    cfg, src, ep, etat, dec, execs, _ = run_ref
    res, v, texte = _rapport(cfg, src, ep, etat, dec, execs)
    assert texte.index("## Verdict") < texte.index("## Univers")
    assert rapport.AVERTISSEMENT in texte and cfg.modele.etiquette_simule in texte
    assert not rapport.formulations_interdites(texte) and not rapport.controler_sharpe_tableaux(
        texte
    )
    assert "Multi-agent (débat)" in texte and "IC de Wilson" in texte and "Kappa" in texte
    assert "SYN08" in texte  # titres sans données publiés
    # avec le mock tout est identique entre exécutions : aucun gain mesurable, jamais « meilleur »
    assert v.statut == "non_concluant"
    # nombre de BUY publié par portefeuille
    assert res["executions"]["baseline"]["risk_averse"]["decompte"]["ET"]["primaire"]["BUY"] >= 0


def test_deux_executions_identiques_donnent_des_sorties_identiques(tmp_path, run_ref):
    sorties = []
    for r in (run_ref, _tout(tmp_path, "b")):
        cfg, src, ep, etat, dec, execs, _ = r
        res, v, texte = _rapport(cfg, src, ep, etat, dec, execs)
        sorties.append((texte, json.dumps(res, sort_keys=True)))
    assert sorties[0] == sorties[1]


def test_reprise_apres_interruption_donne_le_meme_resultat(tmp_path, run_ref):
    cfg, src, ep, settings, fab, _ = _monde(tmp_path)
    (tmp_path / "r").mkdir()
    etat = Etat(tmp_path / "r" / "etat.json", cfg.source_sha256 or "")
    execs = [e.nom for e in cfg.executions]
    with pytest.raises(ReplicationInterrompue) as exc:
        produire_decisions(
            cfg,
            src,
            ep,
            settings,
            etat,
            fab,
            executions=execs,
            univers="pool",
            dossier_cache=None,
            max_debats=7,
        )
    assert exc.value.code == 3 and len(etat.debats) == 7
    etat2 = Etat(
        tmp_path / "r" / "etat.json", cfg.source_sha256 or ""
    )  # relu depuis le fichier d'état
    assert len(etat2.debats) == 7
    dec = produire_decisions(
        cfg, src, ep, settings, etat2, fab, executions=execs, univers="pool", dossier_cache=None
    )
    cfg_b, src_b, ep_b, etat_b, dec_b, _, _ = run_ref
    assert etat2.debats.keys() == etat_b.debats.keys()
    assert {k: v["final"] for k, v in etat2.debats.items()} == {
        k: v["final"] for k, v in etat_b.debats.items()
    }
    assert dec.tirage == dec_b.tirage


def test_reprise_refusee_si_la_configuration_change(tmp_path):
    cfg, *_ = _monde(tmp_path)
    (tmp_path / "x").mkdir()
    Etat(tmp_path / "x" / "etat.json", "aaa").sauver()
    with pytest.raises(ValueError, match="reprise refusée"):
        Etat(tmp_path / "x" / "etat.json", "bbb")


def test_changement_de_modele_servi_arrete_la_replication(tmp_path):
    from amundi_agentic.llm.types import ModeleServiChange

    etat = Etat(tmp_path / "e.json", "k")
    etat.observer_modele("main", "m1")
    etat.observer_modele("main", "m1")
    with pytest.raises(ModeleServiChange):
        etat.observer_modele("main", "m2")


def test_aucune_donnee_posterieure_a_t_n_entre_dans_les_decisions(tmp_path):
    cfg, src, ep, settings, fab, _ = _monde(tmp_path)
    t = cfg.cible.date_decision
    fourn = src.fournisseur_decision(["SYN01", "ZS"], t)
    assert isinstance(fourn, GardeFuture)
    # le monde synthétique contient des barres après t : la couche et la garde doivent les écarter
    brut = fourn._inner._serie("SYN01")
    assert brut.index.max() > pd.Timestamp(t)
    etat = Etat(tmp_path / "t.json", cfg.source_sha256 or "")
    produire_decisions(
        cfg,
        src,
        ep,
        settings,
        etat,
        fab,
        executions=["baseline"],
        univers="primaire",
        dossier_cache=None,
    )


def test_garde_future_leve_sur_toute_donnee_a_t_ou_apres():
    t = date(2024, 2, 1)

    class Fuyard:
        def stock_prices(self, tk):
            return pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-31", "2024-02-01"]))

        def macro_series(self, ids):
            return {
                "x": pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2024-01-02"]),
                        "available_from": pd.to_datetime(["2024-02-02"]),
                    }
                )
            }, {}

        def xbrl_facts(self, tk):
            return pd.DataFrame({"filed": pd.to_datetime(["2024-03-01"])})

    g = GardeFuture(Fuyard(), t)
    for appel in (
        lambda: g.stock_prices("A"),
        lambda: g.macro_series(["x"]),
        lambda: g.xbrl_facts("A"),
    ):
        with pytest.raises(LookAheadError):
            appel()


def test_les_agents_ne_voient_que_des_donnees_anterieures_a_t_pendant_un_run(tmp_path):
    cfg, src, ep, settings, fab, _ = _monde(tmp_path)
    t = cfg.cible.date_decision
    vus: list[GardeFuture] = []
    original = src.fournisseur_decision

    def espion(titres, t_):
        g = original(titres, t_)
        vus.append(g)
        return g

    src.fournisseur_decision = espion  # type: ignore[method-assign]
    etat = Etat(tmp_path / "t.json", cfg.source_sha256 or "")
    produire_decisions(
        cfg,
        src,
        ep,
        settings,
        etat,
        fab,
        executions=["baseline"],
        univers="primaire",
        dossier_cache=None,
    )
    g = vus[0]
    assert g.n_controles > 0 and g.date_max_servie is not None
    assert g.date_max_servie < pd.Timestamp(t)


def test_la_production_des_decisions_n_appelle_jamais_la_performance(tmp_path, monkeypatch):
    def interdit(*a, **k):
        raise AssertionError("code de performance appelé pendant la production des décisions")

    for nom in (
        "mesurer",
        "valeur_portefeuille",
        "fenetre_suivi",
        "taux_quotidiens",
        "taux_moyen",
        "rendements",
    ):
        monkeypatch.setattr(perf_mod, nom, interdit)
    cfg, src, ep, settings, fab, _ = _monde(tmp_path)
    appels_prix: list = []
    monkeypatch.setattr(src, "prix_suivi", lambda *a, **k: appels_prix.append(1))
    monkeypatch.setattr(src, "taux_suivi", lambda *a, **k: appels_prix.append(1))
    etat = Etat(tmp_path / "t.json", cfg.source_sha256 or "")
    produire_decisions(
        cfg,
        src,
        ep,
        settings,
        etat,
        fab,
        executions=["baseline"],
        univers="primaire",
        dossier_cache=None,
    )
    assert not appels_prix and etat.debats


def test_module_de_decisions_n_importe_pas_la_performance():
    import amundi_agentic.evaluation.replication as r

    assert not hasattr(r, "perf") and not hasattr(r, "analyser") and not hasattr(r, "analyse")


def test_performance_n_utilise_aucun_prix_apres_la_fin(run_ref, monkeypatch):
    cfg, src, ep, etat, dec, execs, _ = run_ref
    vus: list = []
    original = src.prix_suivi

    def espion(titres, c):
        df = original(titres, c)
        vus.append(df.index.max())
        return df

    monkeypatch.setattr(src, "prix_suivi", espion)
    res = analyse.analyser(
        cfg, src, etat.debats, etat.donnees["caracteristiques"], dec.tirage, dec.evalues, execs
    )
    assert vus and vus[0] <= pd.Timestamp(cfg.cible.fin_suivi)
    assert res["fenetre"]["fin"] <= str(cfg.cible.fin_suivi)


def test_titre_en_echec_est_remplace_par_le_suivant_de_la_permutation(run_ref):
    cfg, src, ep, etat, dec, execs, _ = run_ref
    tombe = dec.tirage.retenus[0]
    debats = {
        k: (
            {**d, "statut_debat": "echec_donnees", "motif": "x"}
            if k.endswith("|" + tombe) and k.startswith("baseline|")
            else d
        )
        for k, d in etat.debats.items()
    }
    from amundi_agentic.evaluation.replication import echecs_techniques
    from amundi_agentic.evaluation.tirage import tirage_primaire

    ech = echecs_techniques(debats)
    assert set(ech) == {tombe}
    t2 = tirage_primaire(ep.utilisables, hors_pool="ZS", n=4, graine=cfg.tirage.graine, echecs=ech)
    assert tombe not in t2.titres and t2.remplaces[tombe] in t2.titres


def test_commande_plan_et_run_mock(tmp_path, capsys):
    base = Namespace(
        plan=True,
        run=False,
        mock=True,
        mock_llm=False,
        synthetic_data=False,
        llm_profile=None,
        mode="interactif",
        llm_config=None,
        executions="baseline,t07_1",
        univers="primaire",
        out=str(tmp_path),
        reprendre=None,
        max_debats=None,
        secondes_par_appel=None,
        prereg_racine=str(tmp_path / "pr"),
        n_pool_synth=20,
    )
    assert commande.executer_replicate(base) == 0
    sortie = capsys.readouterr().out
    assert (
        "appels LLM au total" in sortie
        and "durée : non estimée" in sortie
        and "SHA-256 de la graine" in sortie
    )
    base.plan, base.run, base.univers = False, True, "primaire"
    assert commande.executer_replicate(base) == 0
    dossiers = [p for p in tmp_path.iterdir() if p.is_dir() and p.name != "pr"]
    assert len(dossiers) == 1
    d = dossiers[0]
    for f in (
        "rapport.md",
        "resultats.json",
        "etat.json",
        "tableau_performance.csv",
        "journal_qualite.csv",
        "titres_exclus.csv",
    ):
        assert (d / f).exists()
    assert "NON CONCLUANT" in (d / "rapport.md").read_text(encoding="utf-8")
    assert [
        p.name for p in tmp_path.iterdir() if p.name != d.name
    ] == []  # rien d'écrit hors du dossier


def test_run_reel_refuse_sans_preenregistrement(tmp_path, capsys):
    a = Namespace(
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
    assert commande.executer_replicate(a) == 2
    assert "pré-enregistrement" in capsys.readouterr().err
    assert not [p for p in tmp_path.iterdir()]
