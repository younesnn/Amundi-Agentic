"""Commande `amundi-agentic views` : les vues et le rapport consolidé d'une date (EX-O1-12, UC-1).

    amundi-agentic views --date 2024-02-01 --profile equilibre --llm-profile dev \
        --mode interactif --out runs/ [--mock] [--stocks AAA,BBB] [--live]

Changer de fournisseur LLM ne demande qu'un changement de `config/llm.yaml` (ou de `--llm-config`) :
ce module ne nomme aucun fournisseur ni modèle et n'importe aucun SDK.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.ports import FakeNewsSummaryTool, NewsSummaryTool, RagTool
from amundi_agentic.agents.prompts import PromptLibrary
from amundi_agentic.agents.providers import (
    PitDataProvider,
    SyntheticData,
    construire_outils_reels,
    rag_synthetique,
)
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.data.settings import CONFIG_DIR, ROOT
from amundi_agentic.data.universe import Universe
from amundi_agentic.debate.run import AVERTISSEMENT, RunOutput, ecrire_sorties, executer
from amundi_agentic.llm import ConfigurationError, LLMClient, MockLLMClient, load_config
from amundi_agentic.schemas import ACTIFS_SANS_VUE, RunRecord

PROFILS = ("prudent", "equilibre", "dynamique", "risk_averse", "risk_neutral")


def ajouter_parseur(sub: Any) -> None:
    v = sub.add_parser("views", help="vues et rapport consolidé d'une date (agents + débat)")
    v.add_argument("--date", required=True, help="date de décision t (AAAA-MM-JJ)")
    v.add_argument("--profile", required=True, choices=PROFILS)
    v.add_argument("--llm-profile", choices=("dev", "prod"), default=None)
    v.add_argument("--mode", choices=("interactif", "evaluation"), default="interactif")
    v.add_argument(
        "--out", default="runs", help="dossier de base ; une sous-dossier horodaté est créé"
    )
    v.add_argument(
        "--mock", action="store_true", help="LLM simulé et données synthétiques (aucun réseau)"
    )
    v.add_argument("--mock-llm", action="store_true", help="LLM simulé, données du stockage local")
    v.add_argument(
        "--synthetic-data", action="store_true", help="données synthétiques (LLM réel du profil)"
    )
    v.add_argument("--stocks", default=None, help="titres (poche titres), séparés par des virgules")
    v.add_argument("--assets", default=None, help="classes d'actifs, séparées par des virgules")
    v.add_argument(
        "--live", action="store_true", help="inclut l'agent Sentiment parmi les votants (D-044)"
    )
    v.add_argument("--seed", type=int, default=None)
    v.add_argument(
        "--llm-config", default=None, help="autre fichier llm.yaml (changement de fournisseur)"
    )
    v.add_argument("--preregistration-sha256", default=None, help="obligatoire en mode évaluation")


def _sha_fichiers(*chemins: Path) -> str:
    h = hashlib.sha256()
    for c in chemins:
        h.update(c.read_bytes() if c.exists() else b"")
    return h.hexdigest()


def _git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() or "inconnu"
    except (OSError, subprocess.SubprocessError):
        return "inconnu"


def _donnees_reelles(t: date, universe: Universe):
    from amundi_agentic.data.pit import PointInTimeStore
    from amundi_agentic.data.settings import DataSettings
    from amundi_agentic.data.store import ParquetStore

    s = DataSettings.load()
    pit = PointInTimeStore(ParquetStore(s.store_dir, s.snapshot_dir), s.config)
    etf_view = None
    try:
        from amundi_agentic.data.connectors.esg_etf_sources import load_for_universe

        etf_view = load_for_universe().as_of(t)
    except Exception as exc:  # noqa: BLE001 - source manuelle absente : états « inconnu », signalé
        print(f"avertissement : source ESG manuelle des ETF indisponible ({type(exc).__name__})")
    return PitDataProvider(pit.as_of(t), universe, etf_view)


def _refus(message: str) -> int:
    print(f"erreur : {message}", file=sys.stderr)
    return 2


def executer_commande(args: Any, argv: list[str] | None = None) -> int:
    """Valide les options (code 2 et message, jamais de trace), puis exécute. Les fichiers
    temporaires du LLM simulé vivent dans un dossier temporaire supprimé en fin de commande."""
    with tempfile.TemporaryDirectory(prefix="amundi-views-") as tmp:
        ancien = tempfile.tempdir
        tempfile.tempdir = tmp  # le cache du LLM simulé est créé ici, puis nettoyé
        try:
            return _executer(args, argv)
        finally:
            tempfile.tempdir = ancien


def _executer(args: Any, argv: list[str] | None) -> int:
    try:
        t = date.fromisoformat(args.date)
    except ValueError:
        return _refus(f"date invalide {args.date!r} (attendu AAAA-MM-JJ)")
    try:
        config = load_config(Path(args.llm_config)) if args.llm_config else load_config()
    except (OSError, ConfigurationError) as exc:
        return _refus(f"configuration LLM illisible : {type(exc).__name__}")
    if args.mode == "evaluation":
        if not args.preregistration_sha256:
            return _refus("mode évaluation : --preregistration-sha256 obligatoire (L1 EX-O5-12)")
        if args.llm_profile != "prod":
            return _refus(
                "le mode évaluation exige --llm-profile prod, explicite (modèles figés, D-024) : "
                "jamais de repli sur le profil par défaut"
            )
    profil_llm = args.llm_profile or config.default_mode
    settings = load_settings()
    universe = Universe.load()
    classes_connues = [c for c in universe.classes if c not in ACTIFS_SANS_VUE]
    if args.assets is not None:
        demandees = [x for x in args.assets.split(",") if x]
        inconnues = [x for x in demandees if x not in universe.classes]
        if inconnues:
            return _refus(f"classes d'actifs inconnues : {inconnues} (config/universe.yaml)")
        classes = [x for x in dict.fromkeys(demandees) if x not in ACTIFS_SANS_VUE]
        if not classes and args.assets:
            return _refus(
                "aucune classe d'actifs valide : le monétaire est l'actif résiduel, sans vue"
            )
    else:
        classes = classes_connues
    debut = datetime.now(UTC)
    run_id = debut.strftime("%Y%m%dT%H%M%SZ")
    dossier = Path(args.out) / run_id
    n = 1
    while dossier.exists():  # deux lancements dans la même seconde : jamais de réécriture
        n += 1
        run_id = f"{debut.strftime('%Y%m%dT%H%M%SZ')}-{n}"
        dossier = Path(args.out) / run_id
    graine = config.defaults.seed if args.seed is None else args.seed

    if args.mock or args.mock_llm:
        llm: LLMClient = MockLLMClient(
            config,
            mode=args.mode,
            profile=profil_llm,
            handler=politique_simulee,
            run_id=run_id,
            run_dir=dossier,
            seed=graine,
        )
    else:
        llm = LLMClient(
            config, mode=args.mode, profile=profil_llm, run_id=run_id, run_dir=dossier, seed=graine
        )
    synthetique = args.mock or args.synthetic_data
    rag: RagTool | None = None
    resume: NewsSummaryTool | None = None
    if synthetique:
        stocks_defaut = list(SyntheticData(t, universe=universe).stocks)
    else:
        stocks_defaut = list(universe.stock_demo_tickers)
    titres = [x for x in args.stocks.split(",") if x] if args.stocks is not None else stocks_defaut
    if len(set(titres)) != len(titres):  # deux débats au même identifiant : refusé, pas deviné
        return _refus(f"titres en double dans --stocks : {titres}")
    if synthetique:
        data = SyntheticData(t, universe=universe, stocks=titres)
        rag = rag_synthetique(t, titres)
        resume = FakeNewsSummaryTool()
    else:
        try:
            data = _donnees_reelles(t, universe)
        except Exception as exc:  # noqa: BLE001 - stockage absent ou illisible : message, pas de trace
            return _refus(f"données point-in-time indisponibles ({type(exc).__name__}) : {exc}")
        rag, resume, avertissements = construire_outils_reels(
            llm, data, Path(os.environ.get("AMUNDI_RAG_DIR", ROOT / ".cache" / "rag"))
        )
        for a in avertissements:
            print(f"avertissement : {a}", file=sys.stderr)
    if len(titres) > settings.debate.max_titres:
        print(
            f"poche titres limitée à {settings.debate.max_titres} titres (D-029) : {len(titres)} demandés",
            file=sys.stderr,
        )
        return 2
    if not classes and not titres:
        return _refus("rien à analyser : aucune classe d'actifs et aucun titre")
    ctx = AgentContext(
        t=t,
        profil=args.profile,
        run_id=run_id,
        llm=llm,
        data=data,
        settings=settings,
        prompts=PromptLibrary(),
        rag=rag,
        summarizer=resume,
    )
    sortie: RunOutput = executer(ctx, classes=classes, titres=titres, live=args.live)

    fin = datetime.now(UTC)
    champs = llm.run_fields()
    execution = {
        "commande": " ".join(argv or sys.argv),
        "options": {k: v for k, v in vars(args).items() if k != "preregistration_sha256"},
        "avertissement": AVERTISSEMENT,
        "prompts_sha256": ctx.prompts.tous(),
        "debate_yaml_sha256": settings.source_sha256,
        "debate_settings": settings.model_dump(mode="json"),
        "appels_par_fournisseur": _par_fournisseur(llm),
        "appels_par_agent": _par_agent(llm),
        "appels_resume_news": ctx.n_appels_resume,
        "donnees": "synthétiques (--mock ou --synthetic-data)"
        if synthetique
        else "stockage point-in-time local",
        "manifeste_donnees": None if synthetique else _manifeste(),
        "exclus_esg": sortie.exclus_esg,
        "debats_echoues": sortie.echecs,
        "interrompu": sortie.interrompu,
    }
    ecrire_sorties(dossier, sortie, execution)
    run = RunRecord(
        run_id=run_id,
        debut=debut,
        fin=fin,
        commande=execution["commande"],
        git_commit=_git_commit(),
        uv_lock_sha256=_sha_fichiers(ROOT / "uv.lock"),
        config_sha256=_sha_fichiers(
            CONFIG_DIR / "debate.yaml", CONFIG_DIR / "universe.yaml", CONFIG_DIR / "esg.yaml"
        ),
        preregistration_sha256=args.preregistration_sha256,
        avertissement=AVERTISSEMENT,
        **champs,
    )
    (dossier / "run.json").write_text(run.model_dump_json(indent=1), encoding="utf-8")
    u = llm.usage()
    print(f"run {run_id} : {len(sortie.vues_finales)} vues, {len(sortie.debats)} débats")
    print(
        f"appels LLM réels : {int(u['appels'])} (cache : {int(u['cache_hits'])}) ; "
        f"par fournisseur : {execution['appels_par_fournisseur']}"
    )
    print(f"sorties : {dossier}")
    if sortie.echecs:
        print(f"débats non terminés : {sortie.echecs}", file=sys.stderr)
    print(f"rapport : {dossier / 'rapport.md'}")
    return 3 if sortie.interrompu else 1 if sortie.echecs else 0


def _par_fournisseur(llm: LLMClient) -> dict[str, int]:
    sortie: dict[str, int] = {}
    for r in llm.records:
        if r.cache_hit or r.erreur is not None:
            continue
        sortie[r.fournisseur] = sortie.get(r.fournisseur, 0) + 1
    return sortie


def _par_agent(llm: LLMClient) -> dict[str, int]:
    sortie: dict[str, int] = {}
    for r in llm.records:
        if r.cache_hit or r.erreur is not None:
            continue
        sortie[r.agent] = sortie.get(r.agent, 0) + 1
    return sortie


def _manifeste() -> Any:
    try:
        from amundi_agentic.data.manifest import data_manifest
        from amundi_agentic.data.settings import DataSettings

        m = data_manifest(DataSettings.load())
        return json.loads(json.dumps(m, default=str))["manifest_sha256"]
    except Exception:  # noqa: BLE001 - manifeste indisponible : signalé, pas bloquant
        return None
