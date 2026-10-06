"""Commande `amundi-agentic views` de bout en bout avec le LLM simulé et des données synthétiques :
vues, rapport consolidé, journaux de débat, RunRecord ; changement de fournisseur par la seule
configuration (EX-O1-12, critères d'acceptation de la phase 3)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

from amundi_agentic.cli import main
from amundi_agentic.schemas import DebateLog, RunRecord, View, coupure

ROOT = Path(__file__).resolve().parents[2]
FAUSSE_CLE = "AIza" + "Sy" + "z" * 33


def lancer(tmp_path, *extra, date_="2024-02-01", profil="equilibre"):
    code = main(
        ["views", "--date", date_, "--profile", profil, "--llm-profile", "dev", "--mock",
         "--out", str(tmp_path / "runs"), *extra]
    )  # fmt: skip
    racine = tmp_path / "runs"
    dossiers = sorted(racine.iterdir()) if racine.exists() else []
    return code, dossiers[-1] if dossiers else None


def test_une_commande_genere_vues_rapport_et_journaux(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAUSSE_CLE)  # une clé présente ne doit fuir nulle part
    code, run = lancer(tmp_path)
    assert code == 0
    sortie = capsys.readouterr().out
    assert "appels LLM réels" in sortie and "vues" in sortie
    for nom in (
        "rapport.md",
        "views.json",
        "esg.json",
        "run.json",
        "execution.json",
        "calls.jsonl",
    ):
        assert (run / nom).is_file(), nom
    # vues : chaque vue cite au moins une source antérieure à la coupure
    vues = [View.model_validate(v) for v in json.loads((run / "views.json").read_text())]
    assert vues and all(v.sources for v in vues)
    limite = coupure(date(2024, 2, 1))
    assert all(s.date_publication < limite for v in vues for s in v.sources)
    # un journal par débat : 1 allocation + 1 par titre
    logs = [DebateLog.model_validate_json(f.read_text()) for f in (run / "debates").glob("*.json")]
    assert sorted(entry.niveau_decision for entry in logs) == ["allocation"] + ["titre"] * 3
    assert all(entry.appels and entry.run_id == run.name for entry in logs)
    # RunRecord : modèles servis, hashes des prompts, graine, configuration
    rec = RunRecord.model_validate_json((run / "run.json").read_text())
    assert rec.graine == 0 and rec.profile == "dev" and len(rec.config_sha256) == 64
    assert rec.avertissement.startswith("Prototype académique")
    ex = json.loads((run / "execution.json").read_text())
    assert ex["prompts_sha256"] and all(len(h) == 64 for h in ex["prompts_sha256"].values())
    assert ex["debate_settings"]["debate"]["r_max"] == 2
    served = {
        json.loads(ligne)["modele_servi"]
        for ligne in (run / "calls.jsonl").read_text().splitlines()
    }
    assert served  # modèles servis enregistrés
    # rapport
    rapport = (run / "rapport.md").read_text()
    assert "Prototype académique" in rapport and "## Vues finales" in rapport
    assert "score ESG absent" in rapport
    # aucune clé dans aucun fichier produit
    for f in run.rglob("*"):
        if f.is_file():
            assert FAUSSE_CLE not in f.read_text(encoding="utf-8")


def test_journaux_en_ajout_seul(tmp_path):
    from amundi_agentic.debate.run import ecrire_sorties

    code, run = lancer(tmp_path)
    assert code == 0
    from amundi_agentic.debate.run import RunOutput

    with pytest.raises(FileExistsError):
        ecrire_sorties(run, RunOutput(), {})


def test_changer_de_fournisseur_ne_demande_qu_un_changement_de_configuration(tmp_path):
    brut = yaml.safe_load((ROOT / "config" / "llm.yaml").read_text(encoding="utf-8"))
    sorties = {}
    for nom, modele in (("a", brut["models"]["dev"]), ("b", "groq/modele-de-test")):
        cfg = {**brut, "models": {**brut["models"], "dev": modele}}
        chemin = tmp_path / f"llm_{nom}.yaml"
        chemin.write_text(yaml.safe_dump(cfg, allow_unicode=True))
        dossier = tmp_path / nom
        dossier.mkdir()
        code, run = lancer(dossier, "--llm-config", str(chemin))
        assert code == 0
        ex = json.loads((run / "execution.json").read_text())
        appels = [json.loads(ligne) for ligne in (run / "calls.jsonl").read_text().splitlines()]
        sorties[nom] = (ex["appels_par_fournisseur"], {a["fournisseur"] for a in appels}, run)
    assert set(sorties["a"][0]) == {"ollama"} and set(sorties["b"][0]) == {"groq"}
    assert sorties["a"][1] == {"ollama"} and sorties["b"][1] == {"groq"}
    # même code, mêmes vues (la politique simulée ne dépend pas du modèle) : seul le fournisseur change
    va = json.loads((sorties["a"][2] / "views.json").read_text())
    vb = json.loads((sorties["b"][2] / "views.json").read_text())
    cle = lambda v: (v["actif"], v["direction"], v["statut"])  # noqa: E731
    assert sorted(map(cle, va)) == sorted(map(cle, vb))


def test_poche_titres_limitee_a_quinze_titres(tmp_path, capsys):
    seize = ",".join(f"T{i}" for i in range(16))
    code, _ = lancer(tmp_path, "--stocks", seize)
    assert code == 2 and "limitée à 15" in capsys.readouterr().err


def test_mode_evaluation_exige_le_preenregistrement(tmp_path, capsys):
    code = main(["views", "--date", "2024-02-01", "--profile", "prudent", "--mode", "evaluation",
                 "--mock", "--out", str(tmp_path)])  # fmt: skip
    assert code == 2 and "preregistration" in capsys.readouterr().err


def test_aucune_donnee_posterieure_a_la_date_dans_les_sources(tmp_path):
    for jour in ("2024-02-01", "2023-06-15"):
        code, run = lancer(tmp_path / jour.replace("-", ""), date_=jour)
        assert code == 0
        t = date.fromisoformat(jour)
        limite = datetime(t.year, t.month, t.day, tzinfo=UTC)
        for v in json.loads((run / "views.json").read_text()):
            for s in v["sources"]:
                assert datetime.fromisoformat(s["date_publication"]) <= limite


def test_la_sous_commande_data_est_conservee(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    aide = capsys.readouterr().out
    assert "data" in aide and "views" in aide


# ------------------------------------------------------------------ pannes du fournisseur
def test_panne_du_fournisseur_sur_un_debat_n_efface_pas_les_autres(tmp_path):
    from agents_helpers import fabrique_ctx

    from amundi_agentic.agents.mock_policy import politique_simulee
    from amundi_agentic.agents.providers import rag_synthetique
    from amundi_agentic.debate.run import ecrire_sorties, executer
    from amundi_agentic.llm.types import ProviderError

    def handler(model, messages):
        if "Agent Fundamental" in messages[0]["content"]:
            raise ProviderError("bad_request", "panne simulée")
        return politique_simulee(model, messages)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    ctx.rag = rag_synthetique(ctx.t, ["AAA", "BBB"])
    sortie = executer(ctx, classes=["or"], titres=["AAA", "BBB"])
    assert [d.log.niveau_decision for d in sortie.debats] == ["allocation"]  # l'allocation survit
    assert set(sortie.echecs) == {"titre-AAA", "titre-BBB"} and sortie.interrompu is None
    assert "Débats non terminés" in sortie.rapport_md
    ecrire_sorties(tmp_path / "out", sortie, {})  # journaux écrits malgré les échecs
    assert (tmp_path / "out" / "views.json").is_file()


def test_quota_epuise_arrete_proprement_et_garde_ce_qui_existe(tmp_path):
    from agents_helpers import fabrique_ctx

    from amundi_agentic.debate.run import executer
    from amundi_agentic.llm.types import ProviderError

    def handler(model, messages):
        raise ProviderError("quota", "429 simulé", 429)

    ctx = fabrique_ctx(tmp_path, handler=handler)
    sortie = executer(ctx, classes=["or"], titres=["AAA"])
    assert sortie.debats == [] and sortie.interrompu and "QuotaEpuise" in sortie.interrompu
    assert list(sortie.echecs) == ["allocation"]  # arrêt : les débats suivants ne sont pas tentés
    assert "relancer la même commande" in sortie.rapport_md
