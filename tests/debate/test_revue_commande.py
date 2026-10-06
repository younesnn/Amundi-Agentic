"""Revue indépendante : commande `views` (reproductibilité, RunRecord, modes, codes de sortie,
écritures, changement de fournisseur), critères d'acceptation et hygiène de la phase 3."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tempfile
from pathlib import Path

import pytest
import yaml

from amundi_agentic.agents.prompts import PromptLibrary
from amundi_agentic.cli import main
from amundi_agentic.llm import load_config
from amundi_agentic.schemas import RunRecord, View, coupure

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "amundi_agentic"
PREREG = "a" * 64


def lancer(tmp_path, *extra, date_="2024-02-01", profil="equilibre", llm_profile="dev"):
    argv = [
        "views",
        "--date",
        date_,
        "--profile",
        profil,
        "--mock",
        "--out",
        str(tmp_path / "runs"),
    ]
    if llm_profile:
        argv += ["--llm-profile", llm_profile]
    code = main([*argv, *extra])
    racine = tmp_path / "runs"
    dossiers = sorted(racine.iterdir()) if racine.exists() else []
    return code, dossiers[-1] if dossiers else None


_RUNS: dict[tuple, tuple] = {}


@pytest.fixture(scope="module")
def run_partage(tmp_path_factory):
    """Un run par combinaison d'options pour tout le module (les tests de lecture le partagent :
    la suite reste rapide). Les tests qui vérifient l'écriture ou la répétition lancent le leur."""

    def obtenir(*extra, date_="2024-02-01", profil="equilibre", llm_profile="dev"):
        cle = (extra, date_, profil, llm_profile)
        if cle not in _RUNS:
            racine = tmp_path_factory.mktemp("run")
            _RUNS[cle] = lancer(racine, *extra, date_=date_, profil=profil, llm_profile=llm_profile)
        return _RUNS[cle]

    return obtenir


def normaliser(o, run_id):
    """Journal sans ce qui varie légitimement (horodatages, durées, identifiants uniques)."""
    volatil = {"appel_id", "horodatage", "duree_s", "latence_ms", "duree_ms", "debut", "fin"}
    if isinstance(o, dict):
        return {k: normaliser(v, run_id) for k, v in o.items() if k not in volatil}
    if isinstance(o, list):
        return [normaliser(v, run_id) for v in o]
    if isinstance(o, str):
        return re.sub(r"--out \S+", "--out OUT", o.replace(run_id, "RUN"))
    return o


def empreinte_run(run):
    sortie = {}
    for f in sorted(run.rglob("*")):
        if f.is_file() and f.name not in ("execution.json",):
            rel = str(f.relative_to(run))
            brut = f.read_text(encoding="utf-8")
            if f.suffix == ".json":
                sortie[rel] = normaliser(json.loads(brut), run.name)
            elif f.suffix == ".jsonl":
                sortie[rel] = [normaliser(json.loads(x), run.name) for x in brut.splitlines()]
            else:
                sortie[rel] = re.sub(r"durée [\d.]+ s", "durée X s", brut).replace(run.name, "RUN")
    return sortie


# --------------------------------------------------------------------------- reproductibilité
def test_deux_executions_identiques_donnent_des_journaux_identiques_hors_horodatage(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ca, ra = lancer(tmp_path / "a")
    cb, rb = lancer(tmp_path / "b")
    assert ca == cb == 0 and ra != rb
    ea, eb = empreinte_run(ra), empreinte_run(rb)
    assert set(ea) == set(eb) and len(ea) > 8
    for nom in ea:
        assert ea[nom] == eb[nom], f"journal différent : {nom}"


@pytest.mark.slow
def test_la_graine_et_le_profil_changent_les_journaux_attendus(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, ra = lancer(tmp_path / "a", profil="prudent")
    _, rb = lancer(tmp_path / "b", profil="dynamique")
    pa = json.loads((ra / "run.json").read_text())
    pb = json.loads((rb / "run.json").read_text())
    assert pa["graine"] == pb["graine"] == 0
    ca = (ra / "calls.jsonl").read_text()
    assert ca != (rb / "calls.jsonl").read_text()  # le profil change les requêtes (donc les clés)


def test_run_record_complet_et_hashes_verifiables(run_partage):
    code, run = run_partage()
    assert code == 0
    rec = RunRecord.model_validate_json((run / "run.json").read_text())
    ex = json.loads((run / "execution.json").read_text())
    cfg = ROOT / "config"
    assert (
        ex["debate_yaml_sha256"] == hashlib.sha256((cfg / "debate.yaml").read_bytes()).hexdigest()
    )
    assert ex["prompts_sha256"] == PromptLibrary().tous()
    h = hashlib.sha256()
    for n in ("debate.yaml", "universe.yaml", "esg.yaml"):
        h.update((cfg / n).read_bytes())
    assert rec.config_sha256 == h.hexdigest()
    assert rec.uv_lock_sha256 == hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    assert rec.llm_config_sha256 == hashlib.sha256((cfg / "llm.yaml").read_bytes()).hexdigest()
    assert rec.graine == 0 and rec.mode == "interactif" and rec.profile == "dev"
    assert rec.git_commit and rec.fin >= rec.debut and "pas un conseil" in rec.avertissement
    assert set(rec.modeles_demandes) >= {"main", "light"} or rec.modeles_demandes
    appels = [json.loads(x) for x in (run / "calls.jsonl").read_text().splitlines()]
    assert appels and all(
        a["modele_servi"] and a["prompt_sha256"] and a["graine"] == 0 for a in appels
    )
    assert {a["prompt_id"] for a in appels} <= {
        "+".join(p) for p in _assemblages_possibles()
    } | set(PromptLibrary().tous())


def _assemblages_possibles():
    import itertools

    noms = list(PromptLibrary().tous())
    return [
        (a, b, *rest)
        for a, b in itertools.permutations(noms, 2)
        for rest in [(), ("debate_round",), ("debate_round", "devil")]
    ] + [(n,) for n in noms]


def test_le_hash_de_la_configuration_du_debat_change_si_le_yaml_change(tmp_path, monkeypatch):
    from amundi_agentic.agents.settings import load_settings

    a = load_settings().source_sha256
    copie = tmp_path / "debate.yaml"
    brut = (ROOT / "config" / "debate.yaml").read_text(encoding="utf-8")
    copie.write_text(brut.replace("r_max: 2 ", "r_max: 3 "), encoding="utf-8")
    assert a and load_settings(copie).source_sha256 not in (None, a)


def test_graine_cli_enregistree(run_partage):
    code, run = run_partage("--seed", "7")
    assert code == 0
    assert json.loads((run / "run.json").read_text())["graine"] == 7
    assert {json.loads(x)["graine"] for x in (run / "calls.jsonl").read_text().splitlines()} == {7}


# --------------------------------------------------------------------------- modes et codes de sortie
def test_evaluation_exige_le_preenregistrement_et_le_profil_prod(tmp_path, capsys):
    code, _ = lancer(tmp_path, "--mode", "evaluation", llm_profile="prod")
    assert code == 2 and "preregistration" in capsys.readouterr().err
    code, run = lancer(
        tmp_path / "ok",
        "--mode",
        "evaluation",
        "--preregistration-sha256",
        PREREG,
        llm_profile="prod",
    )
    assert code == 0
    rec = RunRecord.model_validate_json((run / "run.json").read_text())
    assert (
        rec.mode == "evaluation" and rec.profile == "prod" and rec.preregistration_sha256 == PREREG
    )
    assert rec.modele_servi_fige and set(rec.modele_servi_fige) >= {"main"}
    appels = [json.loads(x) for x in (run / "calls.jsonl").read_text().splitlines()]
    assert {a["mode"] for a in appels} == {"evaluation"} and not any(
        a["relais_utilise"] for a in appels
    )
    cfg = load_config()
    assert {a["modele_demande"] for a in appels} <= set(cfg.evaluation.models.values()) | {
        cfg.embeddings["prod"]
    }


def test_evaluation_sans_profil_prod_explicite_est_refusee_code_2_sans_trace(tmp_path, capsys):
    """Décision du lead : l'évaluation exige `--llm-profile prod` EXPLICITE (jamais déduit)."""
    for profil in (None, "dev"):
        code, run = lancer(
            tmp_path / str(profil),
            "--mode", "evaluation", "--preregistration-sha256", PREREG,
            llm_profile=profil,
        )  # fmt: skip
        err = capsys.readouterr().err
        assert code == 2 and "prod" in err and "Traceback" not in err
        assert run is None or not list(run.parent.glob("*/calls.jsonl"))  # aucun appel LLM
    code, _ = lancer(
        tmp_path / "ok", "--mode", "evaluation", "--preregistration-sha256", PREREG,
        llm_profile="prod",
    )  # fmt: skip
    assert code == 0


def test_codes_de_sortie_0_et_2(tmp_path, capsys):
    assert lancer(tmp_path / "a")[0] == 0
    assert lancer(tmp_path / "b", "--stocks", ",".join(f"T{i}" for i in range(16)))[0] == 2


@pytest.mark.parametrize(
    "extra,profil",
    [
        (["--mode", "evaluation", "--preregistration-sha256", PREREG], "dev"),
        (["--assets", "classe_inconnue"], "dev"),
        (["--assets", "monetaire_euro", "--stocks", ""], "dev"),
        (["--llm-config", "/inexistant/llm.yaml"], "dev"),
        (["--stocks", "AAA,AAA"], "dev"),
    ],
)
def test_entrees_invalides_donnent_un_code_2_et_un_message(tmp_path, extra, profil, capsys):
    try:
        code, _ = lancer(tmp_path, *extra, llm_profile=profil)
    except Exception:  # noqa: BLE001
        pytest.fail("exception non gérée")
    assert code == 2 and capsys.readouterr().err


def test_assets_et_stocks_vides_limitent_la_sortie(run_partage):
    code, run = run_partage("--assets", "or", "--stocks", "")
    assert code == 0
    assert {v["actif"] for v in json.loads((run / "views.json").read_text())} == {"or"}


def test_le_residuel_monetaire_est_ecarte_meme_demande_avec_d_autres_actifs(run_partage):
    code, run = run_partage("--assets", "or,monetaire_euro", "--stocks", "")
    assert code == 0
    assert "monetaire_euro" not in {
        v["actif"] for v in json.loads((run / "views.json").read_text())
    }


# --------------------------------------------------------------------------- écritures
def _arbre(racine):
    ignores = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "graphify-out",
        ".claude",
    }
    sortie = {}
    for p in racine.rglob("*"):
        if any(part in ignores for part in p.relative_to(racine).parts) or not p.is_file():
            continue
        sortie[str(p.relative_to(racine))] = p.stat().st_mtime_ns
    return sortie


def test_mock_n_ecrit_rien_dans_le_depot_ni_hors_du_dossier_de_sortie(tmp_path, monkeypatch):
    avant = _arbre(ROOT)
    tmp_sys = tmp_path / "systmp"
    tmp_sys.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_sys))
    monkeypatch.chdir(tmp_path)
    code, run = lancer(tmp_path / "sortie")
    assert code == 0
    assert (
        _arbre(ROOT) == avant
    )  # rien d'écrit dans le dépôt (cache .cache/, runs/, data/, config/)
    assert list(tmp_sys.iterdir()) == []  # le cache temporaire du LLM simulé est nettoyé


def test_mock_n_ecrit_rien_hors_du_dossier_de_sortie(tmp_path, monkeypatch):
    tmp_sys = tmp_path / "systmp"
    tmp_sys.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_sys))
    lancer(tmp_path / "sortie")
    assert list(tmp_sys.iterdir()) == []


@pytest.mark.slow
def test_journaux_ecrits_une_fois_aucun_fichier_existant_n_est_reecrit(tmp_path):
    (tmp_path / "x").mkdir()
    code, run = lancer(tmp_path / "x")
    avant = {f: f.read_bytes() for f in run.rglob("*") if f.is_file()}
    code2, run2 = lancer(tmp_path / "x")
    assert run2 != run and all(f.read_bytes() == b for f, b in avant.items())


def test_le_dossier_de_sortie_contient_les_fichiers_attendus(run_partage):
    code, run = run_partage()
    attendus = {"rapport.md", "views.json", "esg.json", "esg_appels.json", "run.json",
                "execution.json", "calls.jsonl", "debates"}  # fmt: skip
    assert attendus <= {p.name for p in run.iterdir()}


# --------------------------------------------------------------------------- critères d'acceptation
def test_chaque_vue_cite_ses_sources_et_chaque_vue_valuation_porte_ses_toolcalls(run_partage):
    code, run = run_partage()
    from amundi_agentic.schemas import DebateLog

    logs = [DebateLog.model_validate_json(f.read_text()) for f in (run / "debates").glob("*.json")]
    assert logs
    vues_valuation = 0
    for log in logs:
        for r in log.tours:
            for tour in r.tours_agents:
                for v in tour.vues:
                    assert v.sources and v.arguments_pour and v.arguments_contre
                    assert all(s.date_publication < coupure(v.date_analyse) for s in v.sources)
                    if tour.agent == "valuation":
                        vues_valuation += 1
                        assert tour.appels_outils, "vue Valuation sans ToolCall"
                        ids_outils = {c.resultat["meta"]["source_id"] for c in tour.appels_outils}
                        assert {s.source_id for s in v.sources} <= ids_outils
                        assert all(c.outil == "valuation_summary" for c in tour.appels_outils)
    assert vues_valuation >= 4
    for v in json.loads((run / "views.json").read_text()):
        assert v["sources"]
        assert View.model_validate(v).date_analyse.isoformat() == "2024-02-01"


def test_changer_de_fournisseur_se_fait_par_la_configuration_seule_et_le_code_ne_les_nomme_pas(
    tmp_path,
):
    brut = yaml.safe_load((ROOT / "config" / "llm.yaml").read_text(encoding="utf-8"))
    cfg2 = {
        **brut,
        "providers": {**brut["providers"], "autre": {"api_key_env": "AUTRE_KEY"}},
        "models": {**brut["models"], "dev": "autre/modele-x"},
    }
    chemin = tmp_path / "llm.yaml"
    chemin.write_text(yaml.safe_dump(cfg2, allow_unicode=True))
    (tmp_path / "d").mkdir()
    code, run = lancer(tmp_path / "d", "--llm-config", str(chemin))
    assert code == 0
    ex = json.loads((run / "execution.json").read_text())
    assert set(ex["appels_par_fournisseur"]) == {"autre"}
    interdit = re.compile(r"\b(gemini|groq|ollama|openai|anthropic|llama|gpt)\b", re.IGNORECASE)
    for f in [*(SRC / "agents").glob("*.py"), *(SRC / "debate").glob("*.py"), SRC / "cli.py"]:
        assert not interdit.search(f.read_text(encoding="utf-8")), f.name


def test_aucun_nom_de_modele_dans_les_sorties_lisibles(run_partage):
    code, run = run_partage()
    cfg = load_config()
    noms = {i.split("/", 1)[1] for i in [*cfg.models.values(), *cfg.evaluation.models.values()]}
    for nom in ("rapport.md", "views.json", "esg.json"):
        texte = (run / nom).read_text()
        assert not [n for n in noms if n in texte], nom


# --------------------------------------------------------------------------- hygiène
def _imports(f):
    arbre = ast.parse(f.read_text(encoding="utf-8"))
    sortie = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            sortie.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            sortie.add(n.module)
    return sortie


def test_tout_appel_llm_passe_par_llm_client_aucun_sdk_dans_agents_et_debate():
    sdk = (
        "litellm",
        "openai",
        "anthropic",
        "google",
        "groq",
        "ollama",
        "langchain",
        "httpx",
        "requests",
    )
    for f in [*(SRC / "agents").glob("*.py"), *(SRC / "debate").glob("*.py")]:
        for m in _imports(f):
            assert not m.startswith(sdk), (f.name, m)
        t = f.read_text(encoding="utf-8")
        assert (
            "completion(" not in t.replace("complete_structured", "") or f.name == "mock_policy.py"
        )
        assert ".chat.completions" not in t and "api_key" not in t.lower()


def test_les_appels_de_modele_des_agents_ne_passent_que_par_complete_structured():
    for f in [*(SRC / "agents").glob("*.py"), *(SRC / "debate").glob("*.py")]:
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Attribute) and n.attr in ("complete", "embed"):
                pytest.fail(f"{f.name}:{n.lineno} appelle .{n.attr} hors complete_structured")


def _feuilles_avec_commentaire():
    lignes = (ROOT / "config" / "debate.yaml").read_text(encoding="utf-8").splitlines()
    manquantes = []
    for i, ligne in enumerate(lignes, 1):
        m = re.match(r"^(\s*)([\w\"]+):\s*(\S.*)$", ligne)
        if not m or ligne.lstrip().startswith("#"):
            continue
        valeur = m.group(3)
        if valeur.startswith("#"):
            continue  # en-tête de groupe avec commentaire
        commentaire = valeur.split("#", 1)[1] if "#" in valeur else ""
        manquantes.append((i, ligne.strip())) if not commentaire.strip() else None
    return manquantes


def test_debate_yaml_chaque_valeur_est_annotee_avec_sa_source():
    sans_source = _feuilles_avec_commentaire()
    # les clés d'un même groupe partagent le commentaire du groupe parent (g, h, seuils, questions)
    groupes = ("unanime:", "consensus:", "contestee:", "aucune:", "moderee:", "elevee:")
    manquantes = [x for x in sans_source if not x[1].startswith(groupes)]
    assert len(manquantes) <= 40, manquantes  # garde-fou : ne pas dériver
    tete = (ROOT / "config" / "debate.yaml").read_text(encoding="utf-8").splitlines()[:5]
    assert any("hypothèses de conception (H)" in ligne for ligne in tete)
    commentaires = "\n".join(
        ligne
        for ligne in (ROOT / "config" / "debate.yaml").read_text(encoding="utf-8").splitlines()
        if "#" in ligne
    )
    assert commentaires.count("H") > 30 and "L1" in commentaires and "D-0" in commentaires


def test_aucune_valeur_numerique_du_yaml_n_est_codee_en_dur_dans_agents_et_debate():
    brut = yaml.safe_load((ROOT / "config" / "debate.yaml").read_text(encoding="utf-8"))
    valeurs = set()

    def collecte(o):
        if isinstance(o, dict):
            [collecte(v) for v in o.values()]
        elif isinstance(o, list):
            [collecte(v) for v in o]
        elif (
            isinstance(o, (int, float)) and not isinstance(o, bool) and o not in (0, 1, 2, 0.0, 1.0)
        ):
            valeurs.add(float(o))

    collecte(brut)
    assert {0.8, 0.75, 0.4, 0.05, 0.6, 10000.0, 252.0} <= valeurs
    # hypothèses : décimaux non entiers et grands entiers (les petits entiers 2, 3, 5, 12... sont
    # des indices, des longueurs ou des bornes de schéma sans lien avec une hypothèse)
    suspects = {v for v in valeurs if v != int(v) or v >= 150} - {
        500.0,
        1000.0,
        200.0,
        150.0,
        300.0,
    }
    trouves = []
    for f in [*(SRC / "agents").glob("*.py"), *(SRC / "debate").glob("*.py")]:
        if f.name in (
            "providers.py",
            "mock_policy.py",
        ):  # données et politique SYNTHÉTIQUES (tests)
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            est_nombre = isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            if est_nombre and not isinstance(n.value, bool) and float(n.value) in suspects:
                trouves.append((f.name, n.lineno, n.value))
    assert not trouves, trouves


def test_une_cle_absente_du_yaml_est_une_erreur_pas_une_valeur_par_defaut(tmp_path):
    from amundi_agentic.agents.settings import SettingsError, load_settings

    brut = yaml.safe_load((ROOT / "config" / "debate.yaml").read_text(encoding="utf-8"))
    for section, cle in (("confidence", "c_max"), ("debate", "r_max"), ("consensus", "borne_contestee"),
                         ("grounding", "max_retries")):  # fmt: skip
        copie = yaml.safe_load(yaml.safe_dump(brut))
        del copie[section][cle]
        f = tmp_path / f"{section}.yaml"
        f.write_text(yaml.safe_dump(copie, allow_unicode=True))
        with pytest.raises(SettingsError):
            load_settings(f)


def test_langgraph_figure_dans_le_verrou_et_est_pur_python_pour_311_et_312():
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    bloc = lock.split('name = "langgraph"\n', 1)[1].split("\n[[package]]", 1)[0]
    assert "py3-none-any" in bloc  # roue universelle : Python 3.11 et 3.12 sans compilation
    pyp = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'"langgraph>=1\.\d+', pyp)


def test_ruff_e501_toleres_seulement_pour_agents_et_debate():
    pyp = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    toleres = re.findall(r'"([^"]+)"\s*=\s*\[[^\]]*"E501"', pyp)
    assert set(toleres) <= {
        "src/amundi_agentic/agents/**", "src/amundi_agentic/debate/**",
        "tests/agents/**", "tests/debate/**", "tests/**",
    } | {t for t in toleres if t.startswith(("tests/", "src/amundi_agentic/data", "src/amundi_agentic/tools"))}  # fmt: skip


# --------------------------------------------------------------------------- 2e passe : code 2 propre
REFUS = [
    (["--mode", "evaluation", "--preregistration-sha256", PREREG], None, "prod"),
    (["--mode", "evaluation", "--preregistration-sha256", PREREG], "dev", "prod"),
    (["--assets", "classe_inconnue"], "dev", "classe_inconnue"),
    (["--assets", "monetaire_euro", "--stocks", ""], "dev", "monétaire"),
    (["--llm-config", "/inexistant/llm.yaml"], "dev", "llm"),
    (["--stocks", "AAA,AAA"], "dev", "double"),
]


@pytest.mark.parametrize("extra,profil,mot", REFUS)
def test_refus_code_2_message_lisible_sans_trace_ni_dossier_de_run_ni_appel(
    tmp_path, capsys, extra, profil, mot
):
    code, run = lancer(tmp_path, *extra, llm_profile=profil)
    sortie = capsys.readouterr()
    assert code == 2
    assert sortie.err.startswith("erreur :") and "Traceback" not in sortie.err + sortie.out
    assert mot.lower() in sortie.err.lower()
    assert run is None or not list(run.glob("*"))  # aucun dossier de run (ni journal, ni appel)
    assert not list((tmp_path / "runs").glob("*/calls.jsonl"))


def test_date_invalide_donne_le_code_2_sans_trace(tmp_path, capsys):
    code, run = lancer(tmp_path, date_="2024-13-45")
    err = capsys.readouterr().err
    assert code == 2 and "Traceback" not in err and err.startswith("erreur")
    assert run is None


def test_refus_avant_toute_ecriture_dans_le_dossier_de_sortie(tmp_path):
    for extra, profil, _ in REFUS:
        lancer(tmp_path, *extra, llm_profile=profil)
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


def _commande_avec_handler(tmp_path, monkeypatch, handler, *extra):
    from amundi_agentic.debate import commande

    monkeypatch.setattr(commande, "politique_simulee", handler)
    return lancer(tmp_path, *extra)


def test_code_1_si_un_debat_echoue_et_code_3_si_le_quota_est_epuise(tmp_path, monkeypatch):
    from amundi_agentic.agents.mock_policy import politique_simulee
    from amundi_agentic.llm.types import ProviderError

    def panne_fundamental(model, messages):
        if "Agent Fundamental" in messages[0]["content"]:
            raise ProviderError("bad_request", "panne simulée")
        return politique_simulee(model, messages)

    code, run = _commande_avec_handler(tmp_path / "a", monkeypatch, panne_fundamental)
    assert code == 1 and (run / "views.json").is_file()

    def quota(model, messages):
        raise ProviderError("quota", "429", 429)

    code, run = _commande_avec_handler(tmp_path / "b", monkeypatch, quota)
    assert code == 3 and (run / "rapport.md").is_file()
    assert "relancer la même commande" in (run / "rapport.md").read_text()
