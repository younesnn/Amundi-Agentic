# ruff: noqa: E501, N806, N818
"""Commandes `amundi-agentic preregister` et `amundi-agentic replicate` (D-027, D-065).

    amundi-agentic preregister [--motif TEXTE] [--check] [--verify SHA256] [--show-hash]
    amundi-agentic replicate --plan [--executions baseline,t07_1] [--univers pool|primaire]
    amundi-agentic replicate --run --mock [--out runs/replication]
    amundi-agentic replicate --run --llm-profile dev --mode interactif   (LLM réel du profil)

Raccordement avec `views` : `views --mode evaluation --preregistration-sha256 $(amundi-agentic
preregister --show-hash)` ; `preregister --verify <hash>` dit si ce hash est celui du dernier
enregistrement et si l'état courant y est conforme.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.data.settings import ROOT
from amundi_agentic.evaluation import analyse, rapport
from amundi_agentic.evaluation import preregistration as pr
from amundi_agentic.evaluation.repl_config import ConfigReplicationError, charger_config
from amundi_agentic.evaluation.replication import (
    Etat,
    ReplicationInterrompue,
    construire_plan,
    echecs_techniques,
    produire_decisions,
    rendre_plan,
)
from amundi_agentic.evaluation.sources import (
    SourceReelle,
    SourceReplication,
    SourceSynthetique,
    etat_pool,
)
from amundi_agentic.evaluation.tirage import (
    GraineNonConforme,
    graine_sha256,
    tirage_primaire,
    verifier_graine,
)
from amundi_agentic.llm import ConfigurationError, LLMClient, MockLLMClient, load_config

RACINE_REPLICATION = ROOT / "runs" / "replication"


def ajouter_parseurs(sub: Any) -> None:
    p = sub.add_parser("preregister", help="pré-enregistrement en ajout seul (D-027)")
    p.add_argument(
        "--motif", default=None, help="obligatoire pour une nouvelle version (déviation)"
    )
    p.add_argument(
        "--check", action="store_true", help="compare l'état courant au dernier enregistrement"
    )
    p.add_argument(
        "--verify",
        default=None,
        metavar="SHA256",
        help="vérifie un hash (ex. de views --mode evaluation)",
    )
    p.add_argument(
        "--show-hash", action="store_true", help="affiche le SHA-256 du dernier enregistrement"
    )
    p.add_argument(
        "--sans-manifeste", action="store_true", help="ne calcule pas le manifeste des données"
    )
    p.add_argument(
        "--racine", default=None, help="dossier des enregistrements (défaut : runs/preregistration)"
    )

    r = sub.add_parser("replicate", help="réplication AlphaAgents (D-065)")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--plan", action="store_true", help="affiche le plan et le coût en appels, sans rien lancer"
    )
    g.add_argument("--run", action="store_true", help="exécute (reprise : --reprendre)")
    r.add_argument(
        "--mock", action="store_true", help="LLM simulé et données synthétiques (aucun réseau)"
    )
    r.add_argument("--mock-llm", action="store_true", help="LLM simulé, données du stockage local")
    r.add_argument(
        "--synthetic-data", action="store_true", help="données synthétiques, LLM réel du profil"
    )
    r.add_argument("--llm-profile", choices=("dev", "prod"), default=None)
    r.add_argument("--mode", choices=("interactif", "evaluation"), default="interactif")
    r.add_argument("--llm-config", default=None)
    r.add_argument(
        "--executions", default=None, help="noms séparés par des virgules (défaut : toutes)"
    )
    r.add_argument("--univers", choices=("pool", "primaire"), default="pool")
    r.add_argument("--out", default=None, help="dossier de base (défaut : runs/replication)")
    r.add_argument("--reprendre", default=None, help="dossier d'une réplication interrompue")
    r.add_argument("--max-debats", type=int, default=None)
    r.add_argument(
        "--secondes-par-appel",
        type=float,
        default=None,
        help="paramètre de l'estimation de durée (à mesurer)",
    )
    r.add_argument("--prereg-racine", default=None)
    r.add_argument("--n-pool-synth", type=int, default=24)


def _refus(msg: str) -> int:
    print(f"erreur : {msg}", file=sys.stderr)
    return 2


def _manifeste(args: Any):
    if getattr(args, "sans_manifeste", False):
        return None
    try:
        return SourceReelle().manifeste
    except Exception:  # noqa: BLE001 - stockage absent : manifeste « non calculé », signalé
        return None


# ------------------------------------------------------------------------------- preregister
def executer_preregister(args: Any) -> int:
    try:
        cfg = charger_config()
    except (OSError, ConfigReplicationError) as exc:
        return _refus(f"replication.yaml illisible : {exc}")
    racine = Path(args.racine) if args.racine else None
    manif = _manifeste(args)
    if args.show_hash:
        fichiers = pr.lister(cfg.protocole.nom, racine)
        if not fichiers:
            return _refus("aucun enregistrement")
        print(pr.sha256_fichier(fichiers[-1]))
        return 0
    if args.verify:
        statut, chemin, nom = pr.verifier_sha(args.verify, racine)
        if statut == "inconnu":
            return _refus("hash inconnu : aucun enregistrement ne porte ce SHA-256")
        print(f"hash : enregistrement {chemin.name} de « {nom} » ({statut})")
        try:
            pr.exiger_conforme(args.verify, racine=racine, manifeste=manif)
        except pr.PreenregistrementNonConforme as exc:
            print(f"NON CONFORME : {exc}", file=sys.stderr)
            return 1
        print("conforme : l'état courant correspond à l'enregistrement")
        return 0
    if args.check:
        rv = pr.verifier(cfg, racine=racine, manifeste=manif)
        print(rv.message)
        for e in rv.ecarts:
            print(f"  écart : {e}")
        for p in rv.problemes_chaine:
            print(f"  chaîne : {p}")
        if rv.sha256:
            print(f"dernier enregistrement : {rv.dernier.name} (SHA-256 {rv.sha256})")
        return 0 if rv.ok else 1
    try:
        e = pr.enregistrer(cfg, motif=args.motif, racine=racine, manifeste=manif)
    except pr.RienAChanger as exc:
        print(str(exc))
        return 0
    except pr.PreenregistrementError as exc:
        return _refus(str(exc))
    print(f"enregistrement écrit : {e.chemin} (version {e.version})")
    print(f"SHA-256 de l'enregistrement : {e.sha256}")
    print(
        f"SHA-256 de la graine du tirage (écrit avant tout tirage) : {graine_sha256(cfg.tirage.graine)}"
    )
    for x in e.ecarts:
        print(f"  changement : {x}")
    return 0


# ------------------------------------------------------------------------------- replicate
def _source(args: Any, cfg) -> SourceReplication:
    if args.mock or args.synthetic_data:
        return SourceSynthetique(cfg, n_pool=args.n_pool_synth)
    return SourceReelle()


def executer_replicate(args: Any, argv: list[str] | None = None) -> int:
    with tempfile.TemporaryDirectory(prefix="amundi-replicate-") as tmp:
        ancien = tempfile.tempdir
        tempfile.tempdir = (
            tmp  # caches du LLM simulé : dossier temporaire supprimé en fin de commande
        )
        try:
            return _replicate(args, argv)
        finally:
            tempfile.tempdir = ancien


def _titres_evalues(cfg, ep, univers: str) -> list[str]:
    hors = cfg.pool.titre_hors_pool
    if univers == "pool":
        return sorted({*ep.utilisables, hors})
    return list(
        tirage_primaire(
            ep.utilisables, hors_pool=hors, n=cfg.tirage.n_titres, graine=cfg.tirage.graine
        ).titres
    )


def _replicate(args: Any, argv: list[str] | None) -> int:
    try:
        cfg = charger_config()
        settings = load_settings()
        llm_cfg = load_config(Path(args.llm_config)) if args.llm_config else load_config()
    except (OSError, ConfigReplicationError, ConfigurationError) as exc:
        return _refus(f"configuration illisible : {type(exc).__name__} {exc}")
    noms = [e.nom for e in cfg.executions]
    executions = [x for x in args.executions.split(",") if x] if args.executions else noms
    inconnues = [x for x in executions if x not in noms]
    if inconnues:
        return _refus(f"exécutions inconnues : {inconnues} (config/replication.yaml : {noms})")
    if "baseline" not in executions:
        return _refus("l'exécution baseline est exigée (référence du verdict)")
    mock_llm = args.mock or args.mock_llm
    if args.mode == "evaluation" and args.llm_profile != "prod" and not mock_llm:
        return _refus("le mode évaluation exige --llm-profile prod, explicite (D-024)")
    try:
        source = _source(args, cfg)
        ep = etat_pool(source, cfg)
    except Exception as exc:  # noqa: BLE001 - stockage absent : message, pas de trace
        return _refus(f"données indisponibles ({type(exc).__name__}) : {exc}")
    hors = cfg.pool.titre_hors_pool
    ok_hors, motif_hors = source.eligibilite(hors, cfg)
    if not ok_hors:
        return _refus(f"le titre hors pool {hors} n'est pas utilisable : {motif_hors}")
    titres = _titres_evalues(cfg, ep, args.univers)
    gsha = graine_sha256(cfg.tirage.graine)
    racine_pr = Path(args.prereg_racine) if args.prereg_racine else None

    if args.plan:
        depots = None
        if not source.synthetique:
            depots = {tk: source.depots_texte(tk, cfg.cible.date_decision) or 0 for tk in titres}
        plan = construire_plan(
            cfg,
            ep,
            titres,
            executions,
            settings,
            graine_sha=gsha,
            secondes_par_appel=args.secondes_par_appel,
            depots_texte=depots,
        )
        print(rendre_plan(plan))
        rv = pr.verifier(cfg, racine=racine_pr, manifeste=None)
        print(
            f"pré-enregistrement : {rv.message}" + (f" ({rv.dernier.name})" if rv.dernier else "")
        )
        for e in rv.ecarts[:15]:
            print(f"  écart : {e}")
        return 0

    # ---- pré-enregistrement : exigé pour un run réel, informatif pour un essai simulé
    rv = pr.verifier(
        cfg,
        racine=racine_pr,
        manifeste=None if source.synthetique else getattr(source, "manifeste", None),
    )
    prereg: dict[str, Any] = {
        "statut": "conforme" if rv.ok else ("absent" if rv.dernier is None else "deviation"),
        "sha256": rv.sha256,
        "ecarts": [str(e) for e in rv.ecarts[:20]],
    }
    graine_verifiee = False
    if rv.dernier is not None:
        try:
            verifier_graine(
                cfg.tirage.graine, pr.charger(rv.dernier)["empreintes"]["graine_sha256"]
            )
            graine_verifiee = True
        except GraineNonConforme as exc:
            if not mock_llm:
                return _refus(str(exc))
    if not mock_llm and not (rv.ok and graine_verifiee):
        return _refus(
            "exécution réelle refusée : pré-enregistrement absent, dévié ou graine non vérifiée (`preregister --check`)"
        )

    base = Path(args.out) if args.out else RACINE_REPLICATION
    if args.reprendre:
        out = Path(args.reprendre)
        if not (out / "etat.json").exists():
            return _refus("--reprendre : etat.json absent")
    else:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out, n = base / run_id, 1
        while out.exists():
            n += 1
            out = base / f"{run_id}-{n}"
        out.mkdir(parents=True)
    try:
        etat = Etat(out / "etat.json", cfg.source_sha256 or "")
    except ValueError as exc:
        return _refus(str(exc))
    profil_llm = args.llm_profile or llm_cfg.default_mode

    def fabrique(ex, *, cache_dir):
        conf = llm_cfg.model_copy(
            update={"defaults": llm_cfg.defaults.model_copy(update={"temperature": ex.temperature})}
        )
        kw: dict[str, Any] = {
            "mode": args.mode,
            "profile": profil_llm,
            "run_id": f"replication-{ex.nom}",
            "run_dir": out / "llm" / ex.nom,
            "seed": ex.graine_llm,
        }
        if mock_llm:
            return MockLLMClient(conf, handler=politique_simulee, **kw)
        return LLMClient(conf, cache_dir=cache_dir, **kw)

    def journal(s: str) -> None:
        print(s)

    try:
        dec = produire_decisions(
            cfg,
            source,
            ep,
            settings,
            etat,
            fabrique,
            executions=executions,
            univers=args.univers,
            dossier_cache=None if mock_llm else out / "cache",
            max_debats=args.max_debats,
            journal=journal,
        )
    except ReplicationInterrompue as exc:
        print(f"interrompu : {exc}", file=sys.stderr)
        print(f"reprise : amundi-agentic replicate --run --reprendre {out} (mêmes options)")
        return exc.code
    # ---- mesure après coup : seulement ICI, toutes les décisions étant produites
    res = analyse.analyser(
        cfg,
        source,
        etat.debats,
        etat.donnees["caracteristiques"],
        dec.tirage,
        dec.evalues,
        executions,
    )
    verdict = rapport.calculer_verdict(res, cfg)
    cutoffs = {k: v for k, v in llm_cfg.training_cutoff.items()}
    servis = sorted(
        {v for k, v in etat.donnees["modeles_servis"].items() if k != "embed"}
    )  # modèles de chat seulement
    meta = {
        "etiquettes": rapport.etiquette_modele(servis, cutoffs, cfg, simule=bool(mock_llm)),
        "preenregistrement": prereg,
        "graine_sha256": gsha,
        "graine_verifiee": graine_verifiee,
        "n_pool": len(ep.pool),
        "n_utilisables": len(ep.utilisables),
        "exclus": ep.exclus,
        "remplaces": dec.tirage.remplaces,
        "executions": executions,
        "modeles_servis": {k: v for k, v in etat.donnees["modeles_servis"].items() if k != "embed"},
        "modele_embeddings": etat.donnees["modeles_servis"].get("embed"),
        "simule": bool(mock_llm),
        "synthetique": bool(source.synthetique),
        "qualitatif": observations_qualitatives(res, cfg),
    }
    texte = rapport.rendre_rapport(cfg, res, verdict, meta)
    ecrire_sorties(out, cfg, res, verdict, meta, texte, etat, argv)
    print(f"rapport : {out / 'rapport.md'}")
    print(f"verdict : {verdict.statut}")
    return 0


def observations_qualitatives(res: dict[str, Any], cfg) -> list[tuple[str, str, str]]:
    """Comportements décrits qualitativement par le papier, mesurés ici sur la baseline."""
    b = res["executions"]["baseline"]
    lignes: list[tuple[str, str, str]] = []

    def lecture(cond: bool | None) -> str:
        return "indéterminé" if cond is None else "cohérent" if cond else "différent"

    if {"risk_averse", "risk_neutral"} <= set(cfg.profils):
        ra, rn = b["risk_averse"], b["risk_neutral"]
        nra = ra["decompte"]["multi_agent"]["primaire"]["BUY"]
        nrn = rn["decompte"]["multi_agent"]["primaire"]["BUY"]
        lignes.append(
            (
                "Le profil risk-averse retient moins de titres que le risk-neutral",
                f"BUY multi-agent : {nra} (averse) contre {nrn} (neutre)",
                lecture(None if nra == nrn else nra < nrn),
            )
        )
        sra = [ra["decompte"][k]["primaire"]["BUY"] for k in ("valuation_seul", "fundamental_seul")]
        lignes.append(
            (
                "Risk-averse : le multi-agent est plus resserré que les agents seuls",
                f"BUY : multi-agent {nra}, Valuation {sra[0]}, Fundamental {sra[1]}",
                lecture(None if nra == min(sra) else nra < min(sra)),
            )
        )
        vols = {
            tk: v.get("volatilite_annualisee_avant_t") for tk, v in res["caracteristiques"].items()
        }
        pm = ra["portefeuilles"]["multi_agent"]["titres"]
        vb = [vols[t] for t in pm if vols.get(t) is not None]
        vp = [vols[t] for t in res["titres"]["primaire"] if vols.get(t) is not None]
        if vb and vp:
            lignes.append(
                (
                    "Risk-averse : écarte les titres les plus volatils",
                    f"volatilité moyenne connue à t des titres BUY : {_pc(np.mean(vb))} contre {_pc(np.mean(vp))} pour les 15 titres",
                    lecture(np.mean(vb) < np.mean(vp)),
                )
            )
        else:
            lignes.append(
                (
                    "Risk-averse : écarte les titres les plus volatils",
                    "aucun titre BUY ou volatilité absente",
                    "indéterminé",
                )
            )
        cra, crn = (
            ra["portefeuilles"]["multi_agent"]["cumul"],
            rn["portefeuilles"]["multi_agent"]["cumul"],
        )
        lignes.append(
            (
                "Le risk-neutral obtient un rendement cumulé plus élevé que le risk-averse (multi-agent)",
                f"{_pc(crn)} (neutre) contre {_pc(cra)} (averse), sans inférence",
                lecture(None if cra == crn else crn > cra),
            )
        )
        pmx = ra["portefeuilles"]
        lignes.append(
            (
                "Risk-averse : le multi-agent subit une perte maximale plus faible que les agents seuls",
                f"multi-agent {_pc(pmx['multi_agent']['perte_max'])}, Valuation {_pc(pmx['valuation_seul']['perte_max'])}, Fundamental {_pc(pmx['fundamental_seul']['perte_max'])}",
                lecture(
                    pmx["multi_agent"]["perte_max"]
                    > max(pmx["valuation_seul"]["perte_max"], pmx["fundamental_seul"]["perte_max"])
                ),
            )
        )
    return lignes


def _pc(x: float | None) -> str:
    return "n/d" if x is None else f"{100 * float(x):.2f} %"


def _ecrire_csv(chemin: Path, entete: list[str], lignes: list[list[Any]]) -> None:
    with chemin.open("x", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(entete)
        w.writerows(lignes)


def ecrire_sorties(out: Path, cfg, res, verdict, meta, texte, etat: Etat, argv) -> None:
    """Tout est écrit dans `out` (ajout seul pour les sorties finales)."""
    for nom in (
        "rapport.md",
        "resultats.json",
        "execution.json",
        "tableau_performance.csv",
        "tableau_decisions.csv",
        "tableau_comparaisons.csv",
        "tableau_tirages.csv",
        "tableau_kappa.csv",
        "journal_qualite.csv",
        "sharpe_glissant.csv",
        "titres_exclus.csv",
    ):
        (out / nom).unlink(missing_ok=True)  # reprise : les sorties se régénèrent depuis l'état
    (out / "rapport.md").write_text(texte, encoding="utf-8")
    contenu = {
        "verdict": {
            "statut": verdict.statut,
            "raisons": verdict.raisons,
            "par_profil": verdict.par_profil,
        },
        "meta": {k: v for k, v in meta.items() if k != "qualitatif"},
        "qualitatif": meta["qualitatif"],
        "resultats": {k: v for k, v in res.items() if k != "sharpe_glissant"},
        "versions": {"numpy": np.__version__},
    }
    (out / "resultats.json").write_text(
        json.dumps(contenu, ensure_ascii=False, indent=1, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (out / "execution.json").write_text(
        json.dumps(
            {
                "commande": " ".join(argv or sys.argv),
                "ecrit_le": datetime.now(UTC).isoformat(),
                "durees_s": {k: d["duree_s"] for k, d in etat.debats.items()},
                "appels_par_fournisseur": _agreger(etat),
                "prompts_sha256": res["qualite"],
                "avertissement": rapport.AVERTISSEMENT,
            },
            ensure_ascii=False,
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )
    perf_l, comp_l = [], []
    for ex, par_pf in res["executions"].items():
        for pf, bloc in par_pf.items():
            for nom, d in bloc["portefeuilles"].items():
                ic = d["sharpe_intervalle"] or [None, None]
                perf_l.append(
                    [
                        ex,
                        pf,
                        nom,
                        d["m"],
                        d["cumul"],
                        d["volatilite"],
                        d["sharpe"],
                        ic[0],
                        ic[1],
                        d["perte_max"],
                    ]
                )
            for c in bloc["comparaisons"]:
                comp_l.append(
                    [
                        ex,
                        pf,
                        c["pour"],
                        c["contre"],
                        c["delta"],
                        c["bas"],
                        c["haut"],
                        c["titres_differents"],
                        c.get("desaccord_entre_executions"),
                    ]
                )
    _ecrire_csv(
        out / "tableau_performance.csv",
        [
            "execution",
            "profil",
            "portefeuille",
            "m_buy",
            "cumul",
            "volatilite",
            "sharpe",
            "sharpe_ic_bas",
            "sharpe_ic_haut",
            "perte_max",
        ],
        perf_l,
    )
    _ecrire_csv(
        out / "tableau_comparaisons.csv",
        [
            "execution",
            "profil",
            "pour",
            "contre",
            "delta",
            "ic_bas",
            "ic_haut",
            "titres_differents",
            "desaccord_entre_executions",
        ],
        comp_l,
    )
    dec_l = []
    seuil = cfg.mapping.buy_si_niveau_superieur_a
    from amundi_agentic.evaluation.portefeuilles import PORTEFEUILLES, decisions, etiquette_decision

    for cle, d in sorted(etat.debats.items()):
        ex, pf, tk = cle.split("|")
        if d["statut_debat"] != "ok":
            dec_l.append([ex, pf, tk, d["statut_debat"]] + [""] * len(PORTEFEUILLES))
            continue
        dd = decisions(d, seuil)
        dec_l.append([ex, pf, tk, "ok"] + [etiquette_decision(dd[p]) for p in PORTEFEUILLES])
    _ecrire_csv(
        out / "tableau_decisions.csv",
        ["execution", "profil", "titre", "statut_debat", *PORTEFEUILLES],
        dec_l,
    )
    tir_l = []
    for ex, par in res["secondaires"].get("tableau", {}).items():
        if ex == "ref15":
            continue
        for pf, t in par.items():
            for nom, v in t.items():
                tir_l.append([ex, pf, nom, v["mediane"], v["p05"], v["p95"]])
    _ecrire_csv(
        out / "tableau_tirages.csv",
        ["execution", "profil", "portefeuille", "mediane", "centile_5", "centile_95"],
        tir_l,
    )
    _ecrire_csv(
        out / "tableau_kappa.csv",
        ["profil", "execution", "n", "accords", "frequence", "wilson_bas", "wilson_haut", "kappa"],
        [
            [
                pf,
                ex,
                k["n"],
                k["accords"],
                k["frequence"],
                *(k["wilson"] or [None, None]),
                k["kappa"],
            ]
            for pf, par in res["kappa"].items()
            for ex, k in par.items()
        ],
    )
    q_l = []
    for ex, q in res["qualite"].items():
        for ag, a in q["par_agent"].items():
            q_l.append(
                [
                    ex,
                    ag,
                    a["n_debats"],
                    a["taux_ancrage"],
                    a["taux_abstention"],
                    a["taux_json"],
                    a["taux_panne"],
                    q["taux_voix_unique"],
                ]
            )
    _ecrire_csv(
        out / "journal_qualite.csv",
        [
            "execution",
            "agent",
            "debats",
            "taux_rejet_ancrage",
            "taux_abstention",
            "taux_erreur_json",
            "taux_panne",
            "taux_voix_unique",
        ],
        q_l,
    )
    _ecrire_csv(
        out / "sharpe_glissant.csv",
        ["portefeuille", "date", "sharpe_glissant_sans_intervalle"],
        [[g["portefeuille"], g["date"], g["sharpe_glissant"]] for g in res["sharpe_glissant"]],
    )
    _ecrire_csv(
        out / "titres_exclus.csv", ["titre", "motif"], [[k, v] for k, v in meta["exclus"].items()]
    )
    _ = echecs_techniques


def _agreger(etat: Etat) -> dict[str, int]:
    s: dict[str, int] = {}
    for d in etat.debats.values():
        for k, v in d["par_fournisseur"].items():
            s[k] = s.get(k, 0) + v
    return s
