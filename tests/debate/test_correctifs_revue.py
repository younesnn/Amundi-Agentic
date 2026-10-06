"""Correctifs de la revue : voix unique, allocation entièrement vetoed, entrées de la commande,
nettoyage du dossier temporaire du LLM simulé (nouveaux tests)."""

from __future__ import annotations

import json
import tempfile

import pytest
from agents_helpers import fabrique_ctx
from debate_helpers import scripte

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.cli import main
from amundi_agentic.debate import consensus as cs
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.debate.run import executer
from amundi_agentic.schemas import DebateLog

CLASSES = ["actions_etats_unis", "souverain_euro", "or"]
PREREG = "a" * 64


def _debat_macro_rejete(tmp_path, niveau_valuation=2, **kw):
    """Macro invente un chiffre à chaque appel (rejeté) : seule Valuation reste votante."""
    base = scripte(lambda role, tour, actif: niveau_valuation)

    def handler(model, messages):
        out = json.loads(base(model, messages))
        if "Agent Macro" in messages[0]["content"] and "vues" in out:
            for v in out["vues"]:
                v["arguments_pour"] = ["Le rendement atteint 987,65 %."]
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path, handler=handler, **kw)
    esg = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    votants = construire_votants(ctx, "allocation", live=False)
    return ctx, run_debate(
        ctx, "allocation", CLASSES, votants, Coordinator(), esg, risk_agent=RiskAgent()
    )


def test_voix_unique_jamais_un_consensus(tmp_path):
    ctx, res = _debat_macro_rejete(tmp_path)
    cfg = ctx.settings
    assert res.log.votants == ["valuation"]
    for o in res.log.resultats:
        assert o.statut == "voix_unique"
        assert abs(o.niveau_final) <= cfg.consensus.borne_contestee  # +2 voté, borné à +1
        assert o.niveau_final == 1
        assert o.confiance_finale <= cfg.confidence.plafond_voix_unique < cfg.confidence.c_max
        assert o.tours_utilises == 0  # rien à débattre à un seul votant
    for v in res.vues_finales:
        assert v.statut == "voix_unique" and v.confiance <= cfg.confidence.plafond_voix_unique
    # journalisé et relisible
    assert (
        DebateLog.model_validate_json(res.log.model_dump_json()).resultats[0].statut
        == "voix_unique"
    )


def test_voix_unique_non_transmise_par_defaut(tmp_path):
    ctx, res = _debat_macro_rejete(tmp_path)
    assert ctx.settings.debate.transmettre_voix_unique is False
    assert res.vues_transmises(neutre_transmis=True) == []
    assert len(res.vues_transmises(neutre_transmis=True, voix_unique_transmise=True)) == 3


def test_voix_unique_confiance_plafonnee_meme_si_la_formule_donne_plus(tmp_path):
    cfg = fabrique_ctx(tmp_path).settings.confidence
    brut = cs.confiance(1.0, "unanime", 0, "aucune", cfg)
    assert brut == cfg.c_max > cfg.plafond_voix_unique
    assert cs.confiance(1.0, "voix_unique", 0, "aucune", cfg) == cfg.plafond_voix_unique


def test_min_votants_valides_est_un_parametre(tmp_path):
    # avec un minimum de 1, la même situation redevient « unanime » : le seuil vient de la config
    ctx, res = _debat_macro_rejete(
        tmp_path, settings_overrides={"consensus": {"min_votants_valides": 1}}
    )
    assert {o.statut for o in res.log.resultats} == {"unanime"}


def test_voix_unique_dit_dans_le_rapport(tmp_path):
    ctx = fabrique_ctx(tmp_path, handler=politique_simulee)
    sortie = executer(ctx, classes=["or"], titres=[], live=False)
    assert "voix unique" not in sortie.rapport_md.lower()  # deux votants : pas de voix unique
    ctx2, _ = _debat_macro_rejete(tmp_path / "u")
    sortie2 = executer_voix_unique(ctx2)
    assert "voix unique" in sortie2.rapport_md.lower() and "non transmises" in sortie2.rapport_md


def executer_voix_unique(ctx):
    base = ctx.llm.mock.handler

    def handler(model, messages):
        out = json.loads(base(model, messages))
        if "Agent Macro" in messages[0]["content"] and "vues" in out:
            for v in out["vues"]:
                v["arguments_pour"] = ["Le rendement atteint 987,65 %."]
        return json.dumps(out)

    ctx.llm.mock.handler = handler
    return executer(ctx, classes=["or"], titres=[], live=False)


# --------------------------------------------------------------------------- allocation vetoed
def test_allocation_entierement_vetoed_ecartee_sans_appel_llm_et_titres_traites(tmp_path):
    ctx = fabrique_ctx(tmp_path, settings_overrides={"esg": {"etf_criteres_requis": ["tobacco"]}})
    sortie = executer(ctx, classes=CLASSES, titres=["BBB"], live=False)
    assert "allocation" in sortie.ecartes and "veto" in sortie.ecartes["allocation"]
    assert [d.log.niveau_decision for d in sortie.debats] == ["titre"]
    assert sorted(sortie.exclus_esg) == sorted(CLASSES)
    assert "Débats écartés" in sortie.rapport_md
    # aucun appel LLM n'a concerné l'allocation
    assert all(
        "Agent Macro" not in m["content"] for a in sortie.debats[0].log.appels for m in a.messages
    )


def test_allocation_vetoed_seule_aucune_exception_et_aucun_appel(tmp_path):
    ctx = fabrique_ctx(tmp_path, settings_overrides={"esg": {"etf_criteres_requis": ["tobacco"]}})
    sortie = executer(ctx, classes=CLASSES, titres=[], live=False)
    assert sortie.debats == [] and sortie.vues_finales == []
    # seuls les appels d'explication des vetos (agent ESG) ont lieu : aucun agent d'analyse
    assert {r.agent for r in ctx.llm.records} <= {"esg"}


# --------------------------------------------------------------------------- commande
def _vues(tmp_path, *extra, profil="dev", mode=None):
    args = ["views", "--date", "2024-02-01", "--profile", "equilibre", "--mock",
            "--out", str(tmp_path / "runs"), *extra]  # fmt: skip
    if profil:
        args += ["--llm-profile", profil]
    if mode:
        args += ["--mode", mode]
    return main(args)


@pytest.mark.parametrize(
    "extra,profil,mode,motif",
    [
        (["--preregistration-sha256", PREREG], None, "evaluation", "llm-profile prod"),
        (["--preregistration-sha256", PREREG], "dev", "evaluation", "llm-profile prod"),
        ([], "prod", "evaluation", "preregistration"),
        (["--assets", "classe_inconnue"], "dev", None, "inconnues"),
        (["--assets", "monetaire_euro", "--stocks", ""], "dev", None, "aucune classe"),
        (["--llm-config", "/inexistant/llm.yaml"], "dev", None, "configuration LLM"),
        (["--stocks", "AAA,AAA"], "dev", None, "double"),
        (["--assets", "", "--stocks", ""], "dev", None, "aucune classe"),
    ],
)
def test_entrees_invalides_code_2_message_et_rien_d_ecrit(
    tmp_path, capsys, extra, profil, mode, motif
):
    code = _vues(tmp_path, *extra, profil=profil, mode=mode)
    err = capsys.readouterr().err
    assert code == 2 and motif in err and "Traceback" not in err
    assert not (tmp_path / "runs").exists()  # aucun dossier de run, aucun journal


def test_mock_ne_laisse_rien_dans_le_repertoire_temporaire(tmp_path, monkeypatch):
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(systmp))
    assert _vues(tmp_path / "sortie", "--assets", "or", "--stocks", "") == 0
    assert list(systmp.iterdir()) == []  # le cache du LLM simulé est nettoyé
    assert tempfile.tempdir == str(systmp)  # et le réglage global est restauré


def test_evaluation_avec_profil_prod_explicite_est_acceptee_par_la_validation(tmp_path):
    # profil prod + mock : la validation passe (le client simulé refuse ensuite ou accepte : pas de code 2)
    try:
        code = _vues(
            tmp_path, "--assets", "or", "--stocks", "", "--preregistration-sha256", PREREG,
            profil="prod", mode="evaluation",
        )  # fmt: skip
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"exception non gérée : {exc!r}")
    assert code != 2
