"""Chargeur des prompts de rôle versionnés (`agent_prompts/<nom>_<version>.md`, D-003, EX-O1-06).

Aucun prompt n'est écrit dans le code. Chaque fichier commence par un en-tête YAML :

    ---
    agent: valuation_allocation
    version: v1
    niveau: main          # main ou light (niveau de modèle, config/llm.yaml)
    ---

`load_prompt` renvoie le texte et un `PromptRef` (nom, version, SHA-256 des octets du fichier).
`compose` assemble plusieurs fichiers (rôle, profil de risque, règles communes, tour de débat) et
renvoie un `PromptRef` composite : son SHA-256 est celui de la liste ordonnée des SHA-256 des
fichiers, donc deux assemblages différents n'ont jamais le même hash. Le dictionnaire des hashes
de chaque fichier utilisé est conservé pour l'enregistrement d'exécution.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from amundi_agentic.llm.types import PromptRef

ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = ROOT / "agent_prompts"
VERSION_PAR_DEFAUT = "v1"
_ENTETE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


class PromptError(ValueError):
    """Fichier de prompt absent ou en-tête invalide."""


@dataclass(frozen=True)
class Prompt:
    nom: str
    version: str
    niveau: Literal["main", "light"]
    texte: str  # corps, sans l'en-tête
    ref: PromptRef
    chemin: Path


@dataclass(frozen=True)
class PromptComposite:
    """Assemblage de plusieurs fichiers pour un appel : texte envoyé et référence enregistrée."""

    texte: str
    niveau: Literal["main", "light"]
    ref: PromptRef
    fichiers: dict[str, str] = field(default_factory=dict)  # nom -> sha256 de chaque fichier


class PromptLibrary:
    """Charge et met en cache les prompts d'un dossier (par défaut `agent_prompts/`)."""

    def __init__(self, dossier: Path | None = None, version: str = VERSION_PAR_DEFAUT) -> None:
        self.dossier = Path(dossier) if dossier else PROMPTS_DIR
        self.version = version
        self._cache: dict[str, Prompt] = {}

    def load(self, nom: str) -> Prompt:
        if nom in self._cache:
            return self._cache[nom]
        chemin = self.dossier / f"{nom}_{self.version}.md"
        if not chemin.is_file():
            raise PromptError(f"prompt introuvable : {chemin.name}")
        octets = chemin.read_bytes()
        texte = octets.decode("utf-8")
        m = _ENTETE.match(texte)
        if not m:
            raise PromptError(f"{chemin.name} : en-tête YAML (agent, version, niveau) absent")
        meta = yaml.safe_load(m.group(1)) or {}
        if meta.get("agent") != nom or str(meta.get("version")) != self.version:
            raise PromptError(f"{chemin.name} : en-tête incohérent avec le nom ou la version")
        if meta.get("niveau") not in ("main", "light"):
            raise PromptError(f"{chemin.name} : niveau doit valoir main ou light")
        sha = hashlib.sha256(octets).hexdigest()
        p = Prompt(
            nom=nom,
            version=self.version,
            niveau=meta["niveau"],
            texte=texte[m.end() :].strip(),
            ref=PromptRef(prompt_id=nom, version=self.version, sha256=sha),
            chemin=chemin,
        )
        self._cache[nom] = p
        return p

    def profil(self, profil: str) -> str:
        """Description en langage naturel du profil de risque (section `## <profil>` de profils_v1)."""
        corps = self.load("profils").texte
        sections = re.split(r"^## ", corps, flags=re.MULTILINE)[1:]
        for s in sections:
            titre, _, texte = s.partition("\n")
            if titre.strip() == profil:
                return texte.strip()
        raise PromptError(f"profil {profil!r} absent de profils_{self.version}.md")

    def compose(self, *noms: str, variables: dict[str, str] | None = None) -> PromptComposite:
        """Assemble des fichiers (dans l'ordre) ; `{{variable}}` est remplacée dans le texte.

        Le niveau est celui du premier fichier. Une variable non fournie est une erreur : jamais de
        `{{...}}` envoyé au modèle.
        """
        if not noms:
            raise PromptError("aucun prompt à assembler")
        prompts = [self.load(n) for n in noms]
        texte = "\n\n".join(p.texte for p in prompts)
        for k, v in (variables or {}).items():
            texte = texte.replace("{{" + k + "}}", v)
        restes = re.findall(r"\{\{(\w+)\}\}", texte)
        if restes:
            raise PromptError(f"variables non renseignées : {sorted(set(restes))}")
        fichiers = {p.nom: p.ref.sha256 for p in prompts}
        sha = hashlib.sha256("|".join(f"{n}:{h}" for n, h in fichiers.items()).encode()).hexdigest()
        ref = PromptRef(prompt_id="+".join(noms), version=self.version, sha256=sha)
        return PromptComposite(texte=texte, niveau=prompts[0].niveau, ref=ref, fichiers=fichiers)

    def tous(self) -> dict[str, str]:
        """Hash de chaque fichier de prompt versionné du dossier (pour le `RunRecord`)."""
        sortie: dict[str, str] = {}
        suffixe = f"_{self.version}.md"
        for f in sorted(self.dossier.glob(f"*{suffixe}")):
            nom = f.name.removesuffix(suffixe)
            if not self.est_prompt_de_role(f, nom):
                continue  # fichier d'un autre outil (rag_*, summary_*) : hors de ce registre
            sortie[nom] = self.load(nom).ref.sha256
        return sortie

    def est_prompt_de_role(self, chemin: Path, nom: str) -> bool:
        """Règle explicite : seuls les fichiers dont l'en-tête YAML déclare `agent: <nom>` sont des
        prompts de rôle de ce module ; les autres appartiennent à d'autres outils (tâche A)."""
        m = _ENTETE.match(chemin.read_text(encoding="utf-8"))
        if not m:
            return False
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return False
        return isinstance(meta, dict) and meta.get("agent") == nom


def load_prompt(nom: str, version: str = VERSION_PAR_DEFAUT, dossier: Path | None = None) -> Prompt:
    """Raccourci : charge un prompt et renvoie `Prompt` (dont `ref`)."""
    return PromptLibrary(dossier, version).load(nom)
