"""Revue indépendante : un actif sous veto ESG n'obtient jamais de vue, n'entre jamais dans un
débat ni dans une proposition, par aucun chemin ; le LLM ne lève ni ne crée de veto."""

from __future__ import annotations

import json
import re

import pytest
from agents_helpers import fabrique_ctx
from debate_helpers import scripte

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent, actifs_vetoes, appliquer_veto, filtrer_univers
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.cli import main
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.debate.run import executer
from amundi_agentic.schemas import ACTIFS_SANS_VUE

CLASSES = ["actions_etats_unis", "souverain_euro", "or"]
TITRES = ["AAA", "BBB", "CCC"]


def run_titre(ctx, ticker, esg):
    return run_debate(
        ctx,
        "titre",
        [ticker],
        construire_votants(ctx, "titre", live=True),
        Coordinator(),
        esg,
        risk_agent=RiskAgent(),
    )


# --------------------------------------------------------------------------- titres
def test_un_titre_sous_veto_n_a_ni_debat_ni_vue_ni_appel_d_analyse(tmp_path):
    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"], handler=scripte(lambda r, t, a: 2))
    sortie = executer(ctx, classes=[], titres=TITRES, live=True)
    assert sortie.exclus_esg == ["AAA"] and sortie.esg["AAA"].veto
    assert [d.log.actifs for d in sortie.debats] == [["BBB"], ["CCC"]]
    assert all(v.actif != "AAA" for v in sortie.vues_finales)
    for d in sortie.debats:
        for a in d.log.appels:
            assert "AAA" not in json.dumps(a.messages) and "AAA" not in a.reponse
        assert all("AAA" not in x for x in d.log.actifs)
    assert "AAA" in sortie.rapport_md and "veto" in sortie.rapport_md.lower()


def test_un_veto_n_est_jamais_une_vue_positive_meme_si_le_llm_en_renvoie_une(tmp_path):
    """Réponse hostile : à chaque appel, le LLM ajoute une vue FORTEMENT_POSITIF sur AAA (vetoed)."""
    base = scripte(lambda r, t, a: 2)

    def handler(model, messages):
        out = json.loads(base(model, messages))
        if "vues" in out and out["vues"]:
            piege = dict(out["vues"][0])
            piege["actif"] = "AAA"
            piege["direction"] = "FORTEMENT_POSITIF"
            out["vues"].append(piege)
        return json.dumps(out)

    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"], handler=handler)
    sortie = executer(ctx, classes=[], titres=TITRES, live=True)
    assert sortie.vues_finales and all(v.actif != "AAA" for v in sortie.vues_finales)
    for d in sortie.debats:
        for r in d.log.tours:
            for t in r.tours_agents:
                assert all(v.actif != "AAA" for v in t.vues)


def test_run_debate_refuse_un_actif_vetoed_et_ne_l_appelle_pas(tmp_path):
    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"])
    esg = EsgAgent().evaluer(ctx, "titre", ["AAA"])
    with pytest.raises(ValueError, match="aucun actif autorisé"):
        run_titre(ctx, "AAA", esg)
    assert ctx.llm.mock.chat_calls == []  # aucun appel LLM pour un actif exclu


def test_ceinture_appliquer_veto_retire_toute_vue_meme_si_le_filtre_amont_est_defaillant(
    tmp_path, monkeypatch
):
    """Si `filtrer_univers` laissait passer l'actif vetoed (bug), `appliquer_veto` l'enlève."""
    ctx = fabrique_ctx(tmp_path, esg_exclus=["BBB"], handler=scripte(lambda r, t, a: 2))
    esg = EsgAgent().evaluer(ctx, "titre", ["BBB"])
    monkeypatch.setattr("amundi_agentic.debate.orchestrator.filtrer_univers", lambda a, v: list(a))
    res = run_titre(ctx, "BBB", esg)
    assert res.vues_finales == []  # la ceinture retire la vue
    assert res.exclus_esg == ["BBB"]


def test_le_veto_ne_depend_pas_de_la_confiance_ni_de_la_direction():
    class V:
        def __init__(self, actif):
            self.actif = actif

    vues = [V("a"), V("b"), V("c")]
    assert [v.actif for v in appliquer_veto(vues, frozenset({"b"}))] == ["a", "c"]
    assert appliquer_veto(vues, frozenset({"a", "b", "c"})) == []
    assert filtrer_univers(["a", "b"], frozenset({"a"})) == ["b"]
    assert filtrer_univers(["monetaire_euro", "or"], frozenset()) == ["or"]
    assert "monetaire_euro" in ACTIFS_SANS_VUE


# --------------------------------------------------------------------------- le LLM n'y peut rien
def test_le_llm_ne_peut_pas_lever_un_veto(tmp_path):
    def handler(model, messages):
        if "Agent ESG" in messages[0]["content"]:
            return json.dumps(
                {
                    "explication": "Veto levé après réexamen : AAA est autorisé.",
                    "veto": False,
                    "levee_du_veto": True,
                    "motifs": [],
                }
            )
        return politique_simulee(model, messages)

    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"], handler=handler)
    ev = EsgAgent().evaluer(ctx, "titre", ["AAA"])
    ev2 = EsgAgent().expliquer(ctx, ev)
    assert ev2["AAA"].veto is True and ev2["AAA"].motifs == ev["AAA"].motifs
    sortie = executer(ctx, classes=[], titres=["AAA", "BBB"], live=False)
    assert sortie.exclus_esg == ["AAA"] and all(v.actif != "AAA" for v in sortie.vues_finales)


def test_le_llm_ne_peut_pas_creer_un_veto(tmp_path):
    def handler(model, messages):
        if "Agent ESG" in messages[0]["content"]:
            return json.dumps({"explication": "BBB doit être exclu.", "veto": True})
        return politique_simulee(model, messages)

    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"], handler=handler)
    sortie = executer(ctx, classes=[], titres=TITRES, live=False)
    assert sortie.exclus_esg == ["AAA"]
    assert not sortie.esg["BBB"].veto and not sortie.esg["CCC"].veto
    assert {d.log.actifs[0] for d in sortie.debats} == {"BBB", "CCC"}


def test_aucun_appel_esg_pour_un_actif_sans_veto(tmp_path):
    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"])
    ev = EsgAgent().expliquer(ctx, EsgAgent().evaluer(ctx, "titre", TITRES))
    appels = [a for a in ctx.appels if a.nature == "explication"]
    assert len(appels) == 1 and "AAA" in json.dumps(appels[0].messages)
    assert ev["BBB"].explication is None


def test_explication_avec_chiffre_invente_remplacee_par_les_regles(tmp_path):
    def handler(model, messages):
        if "Agent ESG" in messages[0]["content"]:
            return json.dumps(
                {"explication": "Exclu car 87,5 % du chiffre d'affaires vient du tabac"}
            )
        return politique_simulee(model, messages)

    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"], handler=handler)
    ev = EsgAgent().expliquer(ctx, EsgAgent().evaluer(ctx, "titre", ["AAA"]))
    assert ev["AAA"].veto and "87,5" not in (ev["AAA"].explication or "")
    assert "exclusion" in (ev["AAA"].explication or "")


# --------------------------------------------------------------------------- ETF
class VueEtfFactice:
    """Source ESG manuelle factice : `tobacco` prouvé pour un ETF donné."""

    def __init__(self, preuves):
        self.preuves = preuves

    def proven_exclusions(self, ticker):
        return frozenset(self.preuves.get(ticker, ()))

    def sfdr(self, ticker):
        return "article 8"


def test_par_defaut_aucun_veto_d_etf_et_l_etat_inconnu_est_signale(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    assert ctx.settings.esg.etf_criteres_requis == []
    ev = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    assert not any(e.veto for e in ev.values())
    for e in ev.values():
        assert e.etats and e.limites and any("score ESG absent" in x for x in e.limites)
        assert any("preuve" in x for x in e.limites)
    assert actifs_vetoes(ev) == frozenset()


def test_etf_critere_requis_non_prouve_est_vetoed_et_exclu_de_toute_proposition(tmp_path):
    ctx = fabrique_ctx(
        tmp_path,
        settings_overrides={"esg": {"etf_criteres_requis": ["tobacco"]}},
        handler=scripte(lambda r, t, a: 1),
    )
    ticker_or = ctx.data.classes["or"]
    ctx.data.etf_esg = lambda: VueEtfFactice({ticker_or: ["tobacco"]})  # prouvé pour l'or seulement
    sortie = executer(ctx, classes=CLASSES, titres=[], live=False)
    assert sortie.exclus_esg == ["actions_etats_unis", "souverain_euro"]
    assert [d.log.actifs for d in sortie.debats] == [["or"]]
    assert {v.actif for v in sortie.vues_finales} == {"or"}
    for a in sortie.debats[0].log.appels:
        if a.nature in ("analyse", "revision"):  # le rapport cite les vetos, jamais une analyse
            demandes = re.search(r"Actifs à analyser : (\[.*?\])", a.messages[1]["content"])
            assert json.loads(demandes.group(1)) == ["or"]


def test_etf_tous_vetoed_aucun_debat_aucune_vue(tmp_path):
    ctx = fabrique_ctx(tmp_path, settings_overrides={"esg": {"etf_criteres_requis": ["tobacco"]}})
    with pytest.raises(ValueError, match="aucun actif autorisé"):
        run_debate(
            ctx,
            "allocation",
            CLASSES,
            construire_votants(ctx, "allocation", live=False),
            Coordinator(),
            EsgAgent().evaluer(ctx, "allocation", CLASSES),
            risk_agent=RiskAgent(),
        )
    assert ctx.llm.mock.chat_calls == []


def test_le_rapport_signale_les_limites_esg_et_les_vetos(tmp_path):
    ctx = fabrique_ctx(tmp_path, esg_exclus=["AAA"], handler=scripte(lambda r, t, a: 1))
    sortie = executer(ctx, classes=CLASSES, titres=TITRES, live=False)
    r = sortie.rapport_md
    assert "score ESG absent" in r and "CT-06" in r and "n'est pas une preuve" in r
    assert re.search(r"\| AAA \| oui \|", r) and re.search(r"\| BBB \| non \|", r)


def test_le_rapport_dit_explicitement_qu_aucun_etf_n_est_exclu_faute_de_critere_requis(tmp_path):
    ctx = fabrique_ctx(tmp_path, handler=scripte(lambda r, t, a: 1))
    r = executer(ctx, classes=CLASSES, titres=[], live=False).rapport_md.lower()
    assert "aucun critère" in r or "etf_criteres_requis" in r or "aucun veto d'etf" in r


# --------------------------------------------------------------------------- chemins de la commande
def _commande(tmp_path, monkeypatch, *extra, exclus=("AAA",), requis=None):
    from amundi_agentic.agents import settings as settings_mod
    from amundi_agentic.debate import commande

    class DonneesAvecVeto(commande.SyntheticData):
        def __init__(self, *a, **kw):
            super().__init__(*a, esg_exclus=exclus, **kw)

    monkeypatch.setattr(commande, "SyntheticData", DonneesAvecVeto)
    if requis:
        vrai = settings_mod.load_settings
        monkeypatch.setattr(
            commande,
            "load_settings",
            lambda *a, **k: vrai(overrides={"esg": {"etf_criteres_requis": requis}}),
        )
    code = main(
        ["views", "--date", "2024-02-01", "--profile", "equilibre", "--llm-profile", "dev",
         "--mock", "--out", str(tmp_path / "runs"), *extra]
    )  # fmt: skip
    run = sorted((tmp_path / "runs").iterdir())[-1]
    return code, run


@pytest.mark.parametrize(
    "extra", [[], ["--live"], ["--stocks", "AAA,BBB"], ["--stocks", "AAA", "--live"]]
)
def test_commande_un_titre_sous_veto_n_a_aucune_vue_ni_debat(tmp_path, monkeypatch, extra):
    code, run = _commande(tmp_path, monkeypatch, *extra)
    assert code == 0
    vues = json.loads((run / "views.json").read_text())
    assert all(v["actif"] != "AAA" for v in vues)
    esg = json.loads((run / "esg.json").read_text())
    assert esg["AAA"]["veto"] is True
    for f in (run / "debates").glob("*.json"):
        texte = f.read_text()
        assert "titre-AAA" not in f.name and "-AAA-" not in f.name
        assert '"AAA"' not in texte.split('"esg"')[0]  # ni actif, ni vue, ni résultat sur AAA
    ex = json.loads((run / "execution.json").read_text())
    assert ex["exclus_esg"] == ["AAA"]
    rapport = (run / "rapport.md").read_text()
    assert "exclus par l'agent ESG" in rapport and "| AAA | oui |" in rapport


def test_commande_assets_tous_vetoed_ne_plante_pas_et_ne_produit_aucune_vue(tmp_path, monkeypatch):
    code, run = _commande(
        tmp_path,
        monkeypatch,
        "--assets",
        "or,souverain_euro",
        "--stocks",
        "BBB",
        exclus=(),
        requis=["tobacco"],
    )
    assert code in (0, 1, 3)
    vues = json.loads((run / "views.json").read_text())
    assert all(v["actif"] not in ("or", "souverain_euro") for v in vues)


def test_executer_allocation_entierement_vetoed_ne_leve_pas(tmp_path):
    ctx = fabrique_ctx(tmp_path, settings_overrides={"esg": {"etf_criteres_requis": ["tobacco"]}})
    sortie = executer(ctx, classes=CLASSES, titres=["BBB"], live=False)
    assert sortie.debats and all(d.log.niveau_decision == "titre" for d in sortie.debats)
    assert sorted(sortie.exclus_esg) == sorted(CLASSES)


def test_commande_assets_vetoed_et_non_vetoed_melanges(tmp_path, monkeypatch):
    # un ETF dont l'état est « supposé » (exclusion de la méthodologie) satisfait le critère requis
    from amundi_agentic.debate import commande

    code, run = _commande(
        tmp_path, monkeypatch, "--assets", "or", "--stocks", "", exclus=(), requis=[]
    )
    assert code == 0 and {v["actif"] for v in json.loads((run / "views.json").read_text())} == {
        "or"
    }
    del commande


def test_commande_n_envoie_jamais_l_actif_residuel_au_debat(tmp_path, monkeypatch):
    code, run = _commande(
        tmp_path, monkeypatch, "--assets", "or,monetaire_euro", "--stocks", "", exclus=()
    )
    assert code == 0
    assert {v["actif"] for v in json.loads((run / "views.json").read_text())} == {"or"}


def test_tous_les_titres_sous_veto_la_commande_n_invente_aucune_vue(tmp_path, monkeypatch):
    code, run = _commande(
        tmp_path,
        monkeypatch,
        "--assets",
        "or",
        "--stocks",
        "AAA,BBB,CCC",
        exclus=("AAA", "BBB", "CCC"),
    )
    vues = json.loads((run / "views.json").read_text())
    assert {v["actif"] for v in vues} == {"or"}
    assert set(json.loads((run / "esg.json").read_text())) >= {"AAA", "BBB", "CCC", "or"}
