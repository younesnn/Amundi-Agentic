# ruff: noqa: E501, N806, N818
"""Pré-enregistrement (D-027, L1 §11.6) : empreintes figées AVANT tout run, en ajout seul.

`runs/preregistration/<nom>/<AAAA-MM-JJ>.json` fige les SHA-256 des configurations, des prompts de
rôle, du RAG, du résumé et des paraphrases, de `uv.lock`, du manifeste de données (si disponible), le
protocole entier (`config/replication.yaml`) et le hash de la graine du tirage.

* Ajout seul : un fichier existant n'est jamais réécrit (création exclusive) ; une déviation crée une
  NOUVELLE version datée, qui référence la précédente par son SHA-256 et liste ce qui a changé.
* `verifier` compare l'état courant au dernier enregistrement et liste précisément les écarts.
* Raccordement avec `views --mode evaluation --preregistration-sha256 <hash>` : `verifier_sha` retrouve
  l'enregistrement portant ce hash ; `exiger_conforme` le refuse s'il est inconnu, remplacé par une
  version plus récente ou si l'état courant dévie (voir `amundi-agentic preregister --verify`).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from amundi_agentic.agents.prompts import PROMPTS_DIR, PromptLibrary
from amundi_agentic.data.settings import CONFIG_DIR, ROOT
from amundi_agentic.evaluation.repl_config import (
    ReplicationConfig,
    aplatir,
    charger_config,
)
from amundi_agentic.evaluation.tirage import graine_sha256
from amundi_agentic.tools.text_config import prompt_ref

SCHEMA = "amundi-agentic/preregistration/v1"
RACINE_DEFAUT = ROOT / "runs" / "preregistration"
FICHIERS_CONFIG = (
    "debate.yaml",
    "text_tools.yaml",
    "universe.yaml",
    "esg.yaml",
    "esg_etf_sources.yaml",
    "esg_etf_sources.lock.json",  # registre ESG (empreintes append-only)
    "replication.yaml",
)
NOM_FICHIER = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(\d+))?\.json$")


class PreenregistrementError(RuntimeError):
    """Erreur du pré-enregistrement (message sans secret)."""


class RienAChanger(PreenregistrementError):
    """L'état courant est identique au dernier enregistrement : aucune nouvelle version."""


class MotifRequis(PreenregistrementError):
    """Une déviation exige un motif écrit."""


class PreenregistrementNonConforme(PreenregistrementError):
    """Hash inconnu, version remplacée ou état courant différent de l'enregistrement."""


@dataclass(frozen=True)
class Ecart:
    chemin: str
    avant: Any
    apres: Any

    def __str__(self) -> str:
        return f"{self.chemin} : {_court(self.avant)} -> {_court(self.apres)}"


def _court(v: Any) -> str:
    s = "(absent)" if v is None else str(v)
    return s if len(s) <= 70 else s[:67] + "..."


def sha256_octets(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_fichier(p: Path) -> str:
    return sha256_octets(p.read_bytes())


def _json_sur(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str, sort_keys=True))


def _canonique(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)


# ------------------------------------------------------------------------------- empreintes
def empreintes_courantes(
    cfg: ReplicationConfig,
    *,
    config_dir: Path | None = None,
    prompts_dir: Path | None = None,
    racine: Path | None = None,
    manifeste: Callable[[], str | None] | None = None,
) -> dict[str, Any]:
    """Empreintes de l'état courant. `manifeste` : fonction rendant le `manifest_sha256` des données
    (None ou valeur nulle : « non calculé », signalé tel quel dans l'enregistrement)."""
    cdir = Path(config_dir) if config_dir else CONFIG_DIR
    pdir = Path(prompts_dir) if prompts_dir else PROMPTS_DIR
    rac = Path(racine) if racine else ROOT
    configs: dict[str, Any] = {}
    for f in FICHIERS_CONFIG:
        p = cdir / f
        configs[f] = sha256_fichier(p) if p.exists() else None
    llm = yaml.safe_load((cdir / "llm.yaml").read_text(encoding="utf-8"))
    evaluation = _json_sur(llm.get("evaluation", {}))
    configs["llm.yaml#evaluation"] = sha256_octets(_canonique(evaluation).encode())
    cutoffs = _json_sur(llm.get("training_cutoff", {}))
    modeles = evaluation.get("models", {})
    fin_entr = {
        ident: cutoffs.get(ident.split("/", 1)[-1], cutoffs.get(ident))
        for ident in modeles.values()
    }

    bib = PromptLibrary(pdir)
    roles = bib.tous()
    autres: dict[str, str] = {}
    for f in sorted(pdir.glob("*_v1.md")):
        if f.stem.removesuffix("_v1") in roles:
            continue
        ref, _ = prompt_ref(f.stem, pdir)
        autres[f.stem] = ref.sha256
    paraphrases: dict[str, dict[str, str]] = {}
    pp = rac / cfg.paraphrases.dossier
    for nom in sorted({e.paraphrase for e in cfg.executions if e.paraphrase}):
        d = pp / nom
        paraphrases[nom] = {f.stem: sha256_fichier(f) for f in sorted(d.glob("*_v1.md"))}
        manquants = [
            n for n in cfg.paraphrases.prompts_paraphrases if f"{n}_v1" not in paraphrases[nom]
        ]
        if manquants:
            raise PreenregistrementError(f"paraphrase {nom} : fichiers manquants {manquants}")
    composites = {
        "roles": _composite(roles),
        "rag_et_resume": _composite(autres),
        **{n: _composite(h) for n, h in paraphrases.items()},
    }
    lock = rac / "uv.lock"
    return {
        "configs": configs,
        "modeles_evaluation": {"identifiants": modeles, "fin_entrainement": fin_entr},
        "prompts": {"roles": roles, "rag_et_resume": autres, "paraphrases": paraphrases},
        "prompts_composites": composites,
        "uv_lock_sha256": sha256_fichier(lock) if lock.exists() else None,
        "manifeste_donnees_sha256": manifeste() if manifeste else None,
        "protocole": _json_sur(
            yaml.safe_load((cfg.chemin or cdir / "replication.yaml").read_text(encoding="utf-8"))
        ),
        "graine_sha256": graine_sha256(cfg.tirage.graine),
    }


def _composite(h: dict[str, str]) -> str:
    return sha256_octets("|".join(f"{k}:{v}" for k, v in sorted(h.items())).encode())


def comparer(avant: dict[str, Any], apres: dict[str, Any]) -> list[Ecart]:
    """Écarts précis entre deux jeux d'empreintes (clés aplaties `a.b.c`)."""
    a, b = aplatir(avant), aplatir(apres)
    ecarts: list[Ecart] = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k), b.get(k)
        if va != vb:
            ecarts.append(Ecart(k, va, vb))
    return ecarts


# ------------------------------------------------------------------------------- fichiers
def dossier_nom(nom: str, racine: Path | None = None) -> Path:
    return Path(racine or RACINE_DEFAUT) / nom


def lister(nom: str, racine: Path | None = None) -> list[Path]:
    d = dossier_nom(nom, racine)
    if not d.is_dir():
        return []
    entrees = []
    for p in d.iterdir():
        m = NOM_FICHIER.match(p.name)
        if m:
            entrees.append((m.group(1), int(m.group(2) or 1), p))
    return [p for _, _, p in sorted(entrees)]


def charger(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def verifier_chaine(nom: str, racine: Path | None = None) -> list[str]:
    """Intégrité de la chaîne : chaque version référence le SHA-256 exact du fichier précédent."""
    fichiers = lister(nom, racine)
    problemes: list[str] = []
    for i, p in enumerate(fichiers):
        rec = charger(p)
        if rec.get("schema") != SCHEMA:
            problemes.append(f"{p.name} : schéma inattendu")
        if rec.get("version") != i + 1:
            problemes.append(f"{p.name} : version {rec.get('version')} attendue {i + 1}")
        prec = rec.get("precedente")
        if i == 0:
            if prec is not None:
                problemes.append(f"{p.name} : première version avec une précédente")
        else:
            attendu = sha256_fichier(fichiers[i - 1])
            if not prec or prec.get("sha256") != attendu:
                problemes.append(
                    f"{p.name} : la précédente ({fichiers[i - 1].name}) a été modifiée ou mal référencée"
                )
    return problemes


def _git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() or "inconnu"
    except (OSError, subprocess.SubprocessError):
        return "inconnu"


@dataclass
class Enregistrement:
    chemin: Path
    sha256: str
    version: int
    ecarts: list[Ecart] = field(default_factory=list)


def enregistrer(
    cfg: ReplicationConfig,
    *,
    motif: str | None = None,
    racine: Path | None = None,
    config_dir: Path | None = None,
    prompts_dir: Path | None = None,
    racine_projet: Path | None = None,
    manifeste: Callable[[], str | None] | None = None,
    aujourd_hui: date | None = None,
    maintenant: datetime | None = None,
) -> Enregistrement:
    """Écrit une nouvelle version (ajout seul). Première version : aucun motif requis. Version
    suivante : refusée si rien n'a changé ; un motif écrit est exigé."""
    nom = cfg.protocole.nom
    now = maintenant or datetime.now(UTC)
    jour = aujourd_hui or now.date()
    emp = empreintes_courantes(
        cfg,
        config_dir=config_dir,
        prompts_dir=prompts_dir,
        racine=racine_projet,
        manifeste=manifeste,
    )
    existants = lister(nom, racine)
    if (problemes := verifier_chaine(nom, racine)) and existants:
        raise PreenregistrementError("chaîne d'enregistrements altérée : " + " ; ".join(problemes))
    precedente = None
    ecarts: list[Ecart] = []
    if existants:
        dernier = existants[-1]
        rec_prec = charger(dernier)
        ecarts = comparer(rec_prec["empreintes"], emp)
        if not ecarts:
            raise RienAChanger(f"état identique à {dernier.name} : aucune nouvelle version")
        if not motif or not motif.strip():
            raise MotifRequis("une déviation crée une nouvelle version : --motif est obligatoire")
        precedente = {"fichier": dernier.name, "sha256": sha256_fichier(dernier)}
    version = len(existants) + 1
    record = {
        "schema": SCHEMA,
        "nom": nom,
        "version": version,
        "enregistre_le": now.isoformat(),
        "date": jour.isoformat(),
        "git_commit": _git_commit(),
        "precedente": precedente,
        "motif": motif if precedente else None,
        "changements": [{"chemin": e.chemin, "avant": e.avant, "apres": e.apres} for e in ecarts],
        "tirage_effectue": False,  # le hash de la graine est écrit AVANT tout tirage
        "empreintes": emp,
        "avertissement": "Prototype académique (ESCP, pour Amundi Technology). Ce n'est pas un conseil en investissement.",
    }
    d = dossier_nom(nom, racine)
    d.mkdir(parents=True, exist_ok=True)
    k = 1
    while True:
        cible = d / (f"{jour.isoformat()}.json" if k == 1 else f"{jour.isoformat()}-{k}.json")
        try:
            with cible.open("x", encoding="utf-8") as f:  # création exclusive : jamais d'écrasement
                f.write(json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
            break
        except FileExistsError:
            k += 1
    return Enregistrement(cible, sha256_fichier(cible), version, ecarts)


# ------------------------------------------------------------------------------- vérification
@dataclass
class RapportVerification:
    nom: str
    ok: bool
    dernier: Path | None
    sha256: str | None
    ecarts: list[Ecart] = field(default_factory=list)
    problemes_chaine: list[str] = field(default_factory=list)
    message: str = ""


def verifier(
    cfg: ReplicationConfig,
    *,
    racine: Path | None = None,
    config_dir: Path | None = None,
    prompts_dir: Path | None = None,
    racine_projet: Path | None = None,
    manifeste: Callable[[], str | None] | None = None,
) -> RapportVerification:
    """État courant contre le DERNIER enregistrement : liste précise de ce qui diffère."""
    nom = cfg.protocole.nom
    fichiers = lister(nom, racine)
    if not fichiers:
        return RapportVerification(
            nom, False, None, None, message="aucun enregistrement : lancer `preregister`"
        )
    dernier = fichiers[-1]
    prob = verifier_chaine(nom, racine)
    rec = charger(dernier)
    emp = empreintes_courantes(
        cfg,
        config_dir=config_dir,
        prompts_dir=prompts_dir,
        racine=racine_projet,
        manifeste=manifeste,
    )
    ref = dict(rec["empreintes"])
    if manifeste is None:  # manifeste non demandé : on ne le compare pas (signalé dans le message)
        ref = {**ref, "manifeste_donnees_sha256": emp.get("manifeste_donnees_sha256")}
    ecarts = comparer(ref, emp)
    ok = not ecarts and not prob
    return RapportVerification(
        nom,
        ok,
        dernier,
        sha256_fichier(dernier),
        ecarts,
        prob,
        "conforme au dernier enregistrement"
        if ok
        else "déviation : créer une nouvelle version datée et motivée",
    )


def verifier_sha(sha: str, racine: Path | None = None) -> tuple[str, Path | None, str | None]:
    """Retrouve l'enregistrement portant `sha` (SHA-256 du fichier) : ('courant'|'remplace'|'inconnu',
    chemin, nom). Sert à vérifier le `--preregistration-sha256` du mode évaluation de `views`."""
    base = Path(racine or RACINE_DEFAUT)
    if not base.is_dir():
        return "inconnu", None, None
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        fichiers = lister(d.name, racine)
        for i, p in enumerate(fichiers):
            if sha256_fichier(p) == sha:
                return ("courant" if i == len(fichiers) - 1 else "remplace"), p, d.name
    return "inconnu", None, None


def exiger_conforme(
    sha: str,
    *,
    racine: Path | None = None,
    config_dir: Path | None = None,
    prompts_dir: Path | None = None,
    racine_projet: Path | None = None,
    manifeste: Callable[[], str | None] | None = None,
) -> Path:
    """Garde pour `views --mode evaluation` (D-027 : « un run dont la configuration ne correspond pas
    au hash est refusé »). Lève `PreenregistrementNonConforme` si le hash est inconnu, remplacé par
    une version plus récente, ou si l'état courant dévie de l'enregistrement."""
    statut, chemin, nom = verifier_sha(sha, racine)
    if statut == "inconnu" or chemin is None or nom is None:
        raise PreenregistrementNonConforme("hash de pré-enregistrement inconnu")
    if statut == "remplace":
        raise PreenregistrementNonConforme(
            f"{chemin.name} est remplacé par une version plus récente : utiliser le hash du dernier enregistrement"
        )
    cfg = charger_config(config_dir / "replication.yaml" if config_dir else None)
    if cfg.protocole.nom != nom:
        raise PreenregistrementNonConforme(
            f"l'enregistrement {chemin.name} appartient à « {nom} », protocole courant « {cfg.protocole.nom} »"
        )
    rv = verifier(
        cfg,
        racine=racine,
        config_dir=config_dir,
        prompts_dir=prompts_dir,
        racine_projet=racine_projet,
        manifeste=manifeste,
    )
    if not rv.ok:
        raise PreenregistrementNonConforme(
            "l'état courant dévie du pré-enregistrement : "
            + " ; ".join(
                str(e)
                for e in rv.ecarts[:10] + [Ecart(p, None, None) for p in rv.problemes_chaine][:3]
            )
        )
    return chemin
