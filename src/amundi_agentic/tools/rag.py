# ruff: noqa: E501
"""RAG par sections sur les 10-K et 10-Q d'EDGAR (AlphaAgents §2.2.3 ; L1 §4, EX-O1-14).

Principes :
* découpage par SECTIONS du rapport (Item 1, 1A, 7, 7A, 8... ; pour un 10-Q : Part1-Item2...), avec
  repli explicite (`Document`) quand aucun en-tête n'est reconnu ; un guide d'expert par section
  (`agent_prompts/rag_guide_v1.md`) dit comment la lire ;
* POINT-IN-TIME (risque n°1, D-031) : seuls les dépôts acceptés STRICTEMENT avant la coupure de t
  (t 00:00 Europe/Paris) sont indexés et servis. Le filtre est appliqué à chaque `index_filings` et à
  chaque `query`, sur l'instant d'acceptation, indépendamment de ce que le stockage vectoriel contient
  déjà : un dépôt indexé pour une date ultérieure ne sort jamais pour une date antérieure ;
* embeddings par `LLMClient.embed` uniquement (EX-NF-14) ; stockage local simple : un dossier par
  dépôt, `chunks.json` + `vec-<modèle>.npz` (numpy), similarité cosinus ; cache des vecteurs par
  (dépôt, empreinte du passage, modèle) : reconstruction idempotente, aucun appel si tout est connu ;
* aucun chiffre n'est produit ici : l'outil rend des passages citables (`Source`).

Limites : le découpage repose sur des expressions régulières (en-têtes `Item N.` en début de ligne) ;
un rapport au HTML atypique tombe dans le repli. Les tableaux financiers aplatis en texte sont peu
lisibles pour un modèle d'embedding.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from amundi_agentic.data.connectors.filings import ARCHIVE
from amundi_agentic.data.pit import DataView, cutoff_utc
from amundi_agentic.llm.client import LLMClient
from amundi_agentic.llm.types import PromptRef
from amundi_agentic.schemas import Source
from amundi_agentic.tools.base import ToolError
from amundi_agentic.tools.text_config import (
    PROMPTS_DIR,
    RagConfig,
    load_text_tools_config,
    prompt_ref,
)

log = logging.getLogger(__name__)

GUIDE_NAME = "rag_guide_v1"
QUESTIONS_NAME = "rag_questions_v1"
FALLBACK_SECTION = "Document"
TITRE_INFERE_10Q = "Financial Statements (en-tête Item 1 absent du texte : section inférée de la structure du 10-Q)"
FALLBACK_TITLE = "Document (sections non reconnues)"
SCHEMA_VERSION = "2"  # format des fichiers de l'index ; à changer si `chunks.json` change


class NoFilingsError(ToolError):
    """L'index des dépôts du titre est absent du stockage (société non déclarante ?)."""


# ------------------------------------------------------------------------------ modèles publics
class Passage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    section: str
    score: float
    source: Source
    # True : le découpage par sections a échoué pour ce dépôt (section « Document ») ; la section
    # n'est alors pas une information de lecture. Ajout au contrat initial (défaut False).
    section_fallback: bool = False


class RagResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    question: str
    as_of: date
    passages: list[Passage] = Field(default_factory=list)
    n_chunks_indexed: int
    # Ajouts au contrat initial (défauts vides) : dépôts éligibles dont le découpage par sections a
    # échoué (repli « Document »), qu'ils aient ou non un passage dans `passages`.
    section_fallback: bool = False
    fallback_accessions: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------ sections
TITRES_10K = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity and Share Repurchases",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements With Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}
TITRES_10Q = {
    ("1", "1"): "Financial Statements",
    ("1", "2"): "Management's Discussion and Analysis",
    ("1", "3"): "Quantitative and Qualitative Disclosures About Market Risk",
    ("1", "4"): "Controls and Procedures",
    ("2", "1"): "Legal Proceedings",
    ("2", "1A"): "Risk Factors",
    ("2", "2"): "Unregistered Sales of Equity Securities and Use of Proceeds",
    ("2", "3"): "Defaults Upon Senior Securities",
    ("2", "4"): "Mine Safety Disclosures",
    ("2", "5"): "Other Information",
    ("2", "6"): "Exhibits",
}
_ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4"}

_RE_ITEM = re.compile(
    r"^\s*(?:PART\s+(?P<part>IV|I{1,3})\s*[,.:\-–—]?\s*)?ITEM\s+(?P<item>\d{1,2}\s?[A-C]?)\b"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)
_RE_PART = re.compile(r"^\s*PART\s+(?P<part>IV|I{1,3})\b(?P<rest>.*)$", re.IGNORECASE)


def _titre_valide(rest: str) -> bool:
    """Reste de la ligne d'en-tête : vide, ou ponctuation puis majuscule (« . Risk Factors »).
    « Item 7 of this report... » (minuscule) est un renvoi, pas un en-tête."""
    r = rest.strip()
    if len(r) > 160:
        return False
    if not r:
        return True
    r = r.lstrip(" .:—–-|")
    return not r or not r[0].islower()


def is_10q(form: str) -> bool:
    return form.upper().startswith("10-Q")


@dataclass(frozen=True)
class Section:
    code: str  # clé du guide : « Item 7 » ou « Part1-Item2 » ou « Document »
    title: str
    text: str

    @property
    def label(self) -> str:
        return self.code if self.code == FALLBACK_SECTION else f"{self.code} - {self.title}"


def section_code(label: str) -> str:
    """Clé du guide d'une étiquette de section (`Item 7 - MD&A` -> `Item 7`)."""
    return label.split(" - ", 1)[0].strip() if label != FALLBACK_TITLE else FALLBACK_SECTION


_CONNECTEURS = frozenset(
    [
        "see",
        "in",
        "under",
        "to",
        "of",
        "and",
        "with",
        "at",
        "the",
        "our",
        "this",
        "within",
        "section",
        "sections",
        "also",
        "read",
        "refer",
        "per",
        "by",
        "for",
        "from",
        "on",
        "a",
        "an",
        "or",
        "as",
        "that",
        "which",
        "is",
        "are",
    ]
)


def _est_renvoi(avant: str, apres: str) -> bool:
    """Ligne « Item N » coupée au milieu d'une phrase (renvoi, pas un en-tête) : la ligne précédente
    se termine par une virgule ou un mot de liaison, ou la suivante commence par une minuscule."""
    a = avant.rstrip()
    if a.endswith(","):
        return True
    dernier = re.findall(r"[A-Za-zÀ-ÿ]+$", a)
    if dernier and dernier[0] in _CONNECTEURS:
        return True
    return bool(apres) and apres[0].islower()


def _retirer_tables_des_matieres(
    candidats: list[tuple[int, str, str]], gap: int
) -> list[tuple[int, str, str]]:
    """Retire les blocs de table des matières : au moins 3 en-têtes consécutifs séparés de moins de
    `gap` caractères dont la moitié des sections réapparaissent plus loin (le vrai corps). Un bloc de
    renvois adjacents dont les sections ne réapparaissent pas (Items 7, 7A, 8 « par renvoi ») est
    conservé."""
    garde: list[tuple[int, str, str]] = []
    i = 0
    while i < len(candidats):
        j = i
        vus = {candidats[i][1]}
        # une table des matières cite chaque section une fois : un code déjà vu ouvre le vrai corps
        while (
            j + 1 < len(candidats)
            and candidats[j + 1][0] - candidats[j][0] < gap
            and candidats[j + 1][1] not in vus
        ):
            j += 1
            vus.add(candidats[j][1])
        bloc = candidats[i : j + 1]
        if len(bloc) >= 3:
            codes = {c[1] for c in bloc}
            apres = {c[1] for c in candidats[j + 1 :]}
            if len(codes & apres) * 2 >= len(codes):
                i = j + 1
                continue  # table des matières : écartée
        garde.extend(bloc)
        i = j + 1
    return garde


def split_sections(
    text: str,
    form: str,
    *,
    min_section_chars: int = 400,
    toc_gap_chars: int = 1500,
    max_preamble_chars: int = 80_000,
    min_substantial_sections: int = 3,
) -> list[Section]:
    """Découpe le texte d'un 10-K ou 10-Q en sections.

    Les en-têtes sont des lignes commençant par `Item N` (10-K) ou `Part I, Item N` (10-Q). Étapes :
    1. les renvois coupés au milieu d'une phrase sont écartés ;
    2. les blocs de table des matières (3 en-têtes ou plus à moins de `toc_gap_chars`, dont les
       sections réapparaissent plus loin) sont écartés ;
    3. pour chaque section restante, on retient la première occurrence dont le texte atteint
       `min_section_chars` (les en-têtes courants de page répétés ne comptent donc qu'une fois),
       sinon la plus longue.
    Repli explicite `Document` (aucune section n'est alors nommée) si aucun en-tête n'est retenu, si
    moins de `min_substantial_sections` sections atteignent `min_section_chars`, ou si le préambule
    dépasse `max_preamble_chars` (index de renvois placé en fin de document : Intel).
    """
    q = is_10q(form)
    lignes = text.split("\n")
    debuts, pos = [], 0
    for ligne in lignes:
        debuts.append(pos)
        pos += len(ligne) + 1
    part = "1"
    parts_pos: list[tuple[int, str]] = []  # (position, partie) des lignes « PART I » / « PART II »
    candidats: list[tuple[int, str, str]] = []  # (position, code, titre)
    for n, ligne in enumerate(lignes):
        m = _RE_ITEM.match(ligne)
        mp = None if m else _RE_PART.match(ligne)
        if mp and _titre_valide(mp.group("rest")):
            part = _ROMAN[mp.group("part").upper()]
            parts_pos.append((debuts[n], part))
        elif m and _titre_valide(m.group("rest")):
            avant = next((x.strip() for x in reversed(lignes[:n]) if x.strip()), "")
            apres = next((x.strip() for x in lignes[n + 1 :] if x.strip()), "")
            if _est_renvoi(avant, apres):
                continue
            if m.group("part"):
                part = _ROMAN[m.group("part").upper()]
            item = m.group("item").replace(" ", "").upper()
            if q:
                code = f"Part{part}-Item{item}"
                titre = TITRES_10Q.get((part, item), "")
            else:
                code = f"Item {item}"
                titre = TITRES_10K.get(item, "")
            if titre or not q:
                candidats.append((debuts[n], code, titre or "Section"))
    candidats = _retirer_tables_des_matieres(candidats, toc_gap_chars)
    if not candidats:
        return _repli(text, "aucun en-tête de section reconnu")

    def longueur(i: int) -> int:
        fin = candidats[i + 1][0] if i + 1 < len(candidats) else len(text)
        return fin - candidats[i][0]

    choisis: dict[str, int] = {}
    for _i, (_, code, _) in enumerate(candidats):
        if code in choisis:
            continue
        memes = [j for j, c in enumerate(candidats) if c[1] == code]
        substantiels = [j for j in memes if longueur(j) >= min_section_chars]
        choisis[code] = substantiels[0] if substantiels else max(memes, key=longueur)
    departs = sorted((candidats[j][0], candidats[j][1], candidats[j][2]) for j in choisis.values())
    if q and "Part1-Item1" not in choisis and "Part1-Item2" in choisis:
        # Form 10-Q : la Partie I, Item 1 est toujours « Financial Statements ». Certains dépôts
        # (Zscaler) omettent la ligne « Item 1 » : le texte entre « PART I » et l'Item 2 est alors
        # rattaché à cette section, avec un titre qui dit que l'en-tête est inféré.
        pos2 = candidats[choisis["Part1-Item2"]][0]
        marque = max((p for p, n in parts_pos if n == "1" and p < pos2), default=None)
        if marque is not None and pos2 - marque >= min_section_chars:
            departs.append((marque, "Part1-Item1", TITRE_INFERE_10Q))
            departs.sort()
    sections: list[Section] = []
    avant_texte = text[: departs[0][0]].strip()
    if len(avant_texte) > max_preamble_chars:
        return _repli(
            text, f"préambule de {len(avant_texte)} caractères (index en fin de document ?)"
        )
    if len(avant_texte) >= min_section_chars:
        sections.append(Section("Préambule", "Couverture et introduction", avant_texte))
    for n, (debut, code, titre) in enumerate(departs):
        fin = departs[n + 1][0] if n + 1 < len(departs) else len(text)
        corps = text[debut:fin].strip()
        if corps:
            sections.append(Section(code, titre, corps))
    sections = _detacher_pages_f(sections, min_section_chars)
    utiles = [s for s in sections if s.code != "Préambule" and len(s.text) >= min_section_chars]
    if len(utiles) < min_substantial_sections:
        return _repli(text, f"seulement {len(utiles)} section(s) substantielle(s)")
    return sections


_RE_PAGES_F = re.compile(
    r"^\s*(INDEX TO (?:THE )?(?:CONSOLIDATED )?FINANCIAL STATEMENTS|REPORT OF INDEPENDENT REGISTERED "
    r"PUBLIC ACCOUNTING FIRM|CONSOLIDATED BALANCE SHEETS?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
CODE_PAGES_F = "Annexe-F"
TITRE_PAGES_F = "Financial statement pages placed after the signatures (F-pages)"


def _detacher_pages_f(sections: list[Section], min_chars: int) -> list[Section]:
    """Certains 10-K (Qualcomm) placent les états financiers APRÈS « Item 16 » et les signatures : sans
    ce détachement, ils seraient étiquetés « Item 16 - Form 10-K Summary ». Si la dernière section est
    l'Item 16 et qu'un titre d'états financiers y ouvre au moins 20 000 caractères, ce reste devient la
    section `Annexe-F` (étiquette honnête : pages F placées après les signatures)."""
    if not sections or sections[-1].code != "Item 16":
        return sections
    dernier = sections[-1]
    m = _RE_PAGES_F.search(dernier.text)
    if m is None or m.start() < 20 or len(dernier.text) - m.start() < max(20_000, min_chars):
        return sections
    tete, queue = dernier.text[: m.start()].strip(), dernier.text[m.start() :].strip()
    return [
        *sections[:-1],
        Section(dernier.code, dernier.title, tete),
        Section(CODE_PAGES_F, TITRE_PAGES_F, queue),
    ]


def _repli(text: str, raison: str = "") -> list[Section]:
    log.warning("découpage par sections impossible (%s) : repli sur « Document »", raison)
    corps = text.strip()
    return [Section(FALLBACK_SECTION, FALLBACK_TITLE, corps)] if corps else []


def chunk_text(text: str, *, size: int, overlap: int, min_chars: int) -> list[str]:
    """Passages de `size` caractères au plus : paragraphes regroupés ; un paragraphe plus long est
    coupé aux espaces avec un recouvrement de `overlap`. Les passages de moins de `min_chars`
    caractères sont écartés, sauf s'il n'y en a qu'un (section très courte : « None. »)."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    morceaux: list[str] = []
    courant = ""
    for p in paras:
        if len(p) > size:
            if courant:
                morceaux.append(courant)
                courant = ""
            morceaux.extend(_couper(p, size, overlap))
        elif not courant:
            courant = p
        elif len(courant) + 2 + len(p) <= size:
            courant = f"{courant}\n\n{p}"
        else:
            morceaux.append(courant)
            courant = p
    if courant:
        morceaux.append(courant)
    if len(morceaux) > 1:
        morceaux = [m for m in morceaux if len(m) >= min_chars]
    return morceaux


def _couper(p: str, size: int, overlap: int) -> list[str]:
    sortie, debut = [], 0
    overlap = min(overlap, size // 2)
    while debut < len(p):
        fin = min(debut + size, len(p))
        if fin < len(p):
            coupe = p.rfind(" ", debut + size // 2, fin)
            fin = coupe if coupe > debut else fin
        sortie.append(p[debut:fin].strip())
        if fin >= len(p):
            break
        debut = max(fin - overlap, debut + 1)
    return [s for s in sortie if s]


# ------------------------------------------------------------------------------ guide et questions
def load_guide(prompts_dir: Path | None = None) -> dict[str, str]:
    """Guide d'expert par section : {clé (`Item 7`, `Part1-Item2`, `Général`, `Document`): texte}."""
    _, texte = prompt_ref(GUIDE_NAME, prompts_dir)
    guide: dict[str, str] = {}
    cle: str | None = None
    corps: list[str] = []
    for ligne in texte.splitlines():
        if ligne.startswith("## "):
            if cle is not None:
                guide[cle] = "\n".join(corps).strip()
            cle, corps = ligne[3:].strip(), []
        elif cle is not None:
            corps.append(ligne)
    if cle is not None:
        guide[cle] = "\n".join(corps).strip()
    return guide


class RagQuestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    core: bool
    sections: tuple[str, ...]
    question: str


def load_questions(
    *, include_optional: bool = False, prompts_dir: Path | None = None
) -> list[RagQuestion]:
    """Questions fixes de l'agent Fundamental, dans l'ordre du fichier. Par défaut les quatre
    questions du papier (`core`, q = 4 dans le budget de L1 §11.2)."""
    _, texte = prompt_ref(QUESTIONS_NAME, prompts_dir)
    sortie = []
    for ligne in texte.splitlines():
        if not ligne.startswith("- "):
            continue
        id_, statut, sections, question = (x.strip() for x in ligne[2:].split("|", 3))
        q = RagQuestion(
            id=id_,
            core=statut == "core",
            sections=tuple(s.strip() for s in sections.split(",") if s.strip()),
            question=question,
        )
        if q.core or include_optional:
            sortie.append(q)
    return sortie


def rag_prompt_refs(prompts_dir: Path | None = None) -> dict[str, PromptRef]:
    """Références (identifiant, version, SHA-256 du fichier) du guide et des questions."""
    return {n: prompt_ref(n, prompts_dir)[0] for n in (GUIDE_NAME, QUESTIONS_NAME)}


def guide_for(sections: list[str], guide: dict[str, str] | None = None) -> str:
    """Texte du guide d'expert pour les sections données (préfixé du guide général), à joindre
    aux passages dans le message à l'agent. Une section sans guide est signalée telle quelle."""
    g = guide if guide is not None else load_guide()
    blocs = [f"[Guide général]\n{g.get('Général', '')}"]
    vus: set[str] = set()
    for s in sections:
        code = section_code(s)
        if code in vus:
            continue
        vus.add(code)
        blocs.append(f"[Guide {code}]\n{g.get(code, '(pas de guide pour cette section)')}")
    return "\n\n".join(blocs)


# ------------------------------------------------------------------------------ index
def _slug(nom: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nom)


def _sha(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _ecrire_atomique(chemin: Path, ecrire) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(f".tmp-{os.getpid()}-{chemin.name}")
    try:
        ecrire(tmp)
        os.replace(tmp, chemin)
    finally:
        tmp.unlink(missing_ok=True)


@dataclass
class _Depot:
    """Un dépôt indexé en mémoire : ses métadonnées, ses passages et leurs vecteurs unitaires."""

    ticker: str
    accession: str
    form: str
    cik: str
    accepted_utc: datetime
    filing_date: date
    report_date: date | None
    primary_document: str
    chunks: list[dict[str, Any]]
    vectors: np.ndarray

    @property
    def section_fallback(self) -> bool:
        return any(c["section_code"] == FALLBACK_SECTION for c in self.chunks)


class FilingsRAG:
    """RAG sur les 10-K et 10-Q ; voir le module. `data_view` est un `PointInTimeStore` (de
    préférence : `as_of(t)` est appelé pour chaque date) ou un `DataView` (alors `as_of` ne doit pas
    dépasser sa date t)."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        store_dir: Path,
        data_view: Any = None,
        config: RagConfig | None = None,
        prompts_dir: Path | None = None,
    ) -> None:
        self.llm = llm
        self.store_dir = Path(store_dir)
        self.data_view = data_view
        self.config = config or load_text_tools_config().rag
        self.prompt_refs = rag_prompt_refs(prompts_dir)
        self._mem: dict[tuple[str, str, str], _Depot] = {}
        self.n_embedding_calls = 0  # appels réels à `LLMClient.embed` (hors cache du client)

    # --------------------------------------------------------------------- vues et éligibilité
    def _view(self, as_of: date) -> DataView:
        cutoff_utc(as_of)  # refuse un datetime
        dv = self.data_view
        if dv is None:
            raise ValueError(
                "FilingsRAG sans data_view : fournir un PointInTimeStore ou un DataView"
            )
        if isinstance(dv, DataView):
            if as_of > dv.t:
                raise ValueError(f"as_of={as_of} postérieur à la date {dv.t} de la vue fournie")
            return dv
        return dv.as_of(as_of)

    def _eligibles(self, ticker: str, as_of: date) -> tuple[DataView, list]:
        """Dépôts 10-K et 10-Q acceptés STRICTEMENT avant la coupure de `as_of` (filtre appliqué ici
        même si la vue a déjà filtré : double garde), les `max_filings` plus récents."""
        vue = self._view(as_of)
        try:
            depots = vue.filings(ticker, set(self.config.forms))
        except KeyError:
            raise NoFilingsError(f"index des dépôts absent pour {ticker}") from None
        coupure = cutoff_utc(as_of).to_pydatetime()
        ok = [d for d in depots if d.accepted_utc < coupure and d.has_text]
        ok.sort(key=lambda d: (d.accepted_utc, d.accession), reverse=True)
        return vue, ok[: self.config.max_filings]

    # --------------------------------------------------------------------- construction
    def _prefixe(self, kind: str) -> str:
        p = self.config.prefixes.get(self.llm.profile)
        return getattr(p, kind) if p else ""

    def _modele(self) -> str:
        return self.llm.config.embedding_model(self.llm.profile)

    def _dossier(self, ticker: str, accession: str) -> Path:
        return self.store_dir / ticker.upper() / accession

    def _params(self) -> dict[str, Any]:
        c = self.config
        return {
            "chunk_chars": c.chunk_chars,
            "overlap_chars": c.overlap_chars,
            "min_chunk_chars": c.min_chunk_chars,
            "min_section_chars": c.min_section_chars,
            "toc_gap_chars": c.toc_gap_chars,
            "max_preamble_chars": c.max_preamble_chars,
            "min_substantial_sections": c.min_substantial_sections,
            "schema": SCHEMA_VERSION,
        }

    def _chunks_du_depot(self, vue: DataView, d, dossier: Path) -> list[dict[str, Any]]:
        """Passages du dépôt : relus de `chunks.json` si le texte et les paramètres sont inchangés,
        sinon recalculés depuis le texte du stockage."""
        texte = vue.filing_text(d.ticker, d.accession)
        if not texte:
            return []
        empreinte = _sha(texte)
        fichier = dossier / "chunks.json"
        if fichier.is_file():
            try:
                existant = json.loads(fichier.read_text(encoding="utf-8"))
                if existant.get("text_sha256") == empreinte and existant.get("params") == (
                    self._params()
                ):
                    return existant["chunks"]
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # index illisible : reconstruit
        c = self.config
        chunks: list[dict[str, Any]] = []
        sections = split_sections(
            texte,
            d.form,
            min_section_chars=c.min_section_chars,
            toc_gap_chars=c.toc_gap_chars,
            max_preamble_chars=c.max_preamble_chars,
            min_substantial_sections=c.min_substantial_sections,
        )
        for s in sections:
            for i, t in enumerate(
                chunk_text(
                    s.text, size=c.chunk_chars, overlap=c.overlap_chars, min_chars=c.min_chunk_chars
                )
            ):
                chunks.append(
                    {
                        "idx": len(chunks),
                        "section": s.label,
                        "section_code": s.code,
                        "n_in_section": i,
                        "text": t,
                        "fp": _sha(f"{s.code}\n{t}")[:16],
                    }
                )
        meta = {
            "ticker": d.ticker.upper(),
            "accession": d.accession,
            "form": d.form,
            "text_sha256": empreinte,
            "params": self._params(),
            "section_fallback": any(s.code == FALLBACK_SECTION for s in sections),
            "prompts": {n: r.sha256 for n, r in self.prompt_refs.items()},
            "chunks": chunks,
        }
        _ecrire_atomique(
            fichier,
            lambda p: p.write_text(
                json.dumps(meta, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8"
            ),
        )
        return chunks

    def _vecteurs(self, d, chunks: list[dict[str, Any]], dossier: Path) -> np.ndarray:
        """Matrice des vecteurs unitaires (un par passage). Cache par (dépôt, empreinte, modèle) :
        seuls les passages sans vecteur connu sont envoyés à `LLMClient.embed`."""
        modele = self._modele()
        fichier = dossier / f"vec-{_slug(modele)}.npz"
        connus: dict[str, np.ndarray] = {}
        if fichier.is_file():
            try:
                with np.load(fichier, allow_pickle=False) as z:
                    connus = dict(zip(z["fps"].tolist(), z["vectors"], strict=True))
            except (ValueError, OSError, KeyError):
                connus = {}  # fichier illisible : recalculé
        manquants = [c for c in chunks if c["fp"] not in connus]
        # un même texte dans deux passages : un seul vecteur
        uniques = list({c["fp"]: c for c in manquants}.values())
        prefixe = self._prefixe("document")
        date_depot = d.accepted_utc.astimezone(UTC).date()  # EX-NF-04 : date d'acceptation du dépôt
        pas = self.config.embed_batch
        for i in range(0, len(uniques), pas):
            lot = uniques[i : i + pas]
            res = self.llm.embed(
                [prefixe + f"{c['section']}\n{c['text']}" for c in lot],
                date_donnees=date_depot,
                agent="rag_index",
            )
            self.n_embedding_calls += 1
            if len(res.vectors) != len(lot):
                raise ToolError("nombre de vecteurs différent du nombre de passages envoyés")
            for c, v in zip(lot, res.vectors, strict=True):
                connus[c["fp"]] = np.asarray(v, dtype=np.float32)
        if uniques or not fichier.is_file():
            fps = [c["fp"] for c in chunks]
            mat = (
                np.stack([connus[f] for f in fps]).astype(np.float32)
                if fps
                else np.zeros((0, 0), np.float32)
            )
            _ecrire_atomique(
                fichier,
                lambda p: np.savez(p.open("wb"), fps=np.array(fps, dtype="<U16"), vectors=mat),
            )
        if not chunks:
            return np.zeros((0, 0), np.float32)
        mat = np.stack([connus[c["fp"]] for c in chunks]).astype(np.float64)
        normes = np.linalg.norm(mat, axis=1, keepdims=True)
        return mat / np.where(normes == 0, 1.0, normes)

    def _depot(self, vue: DataView, d) -> _Depot:
        cle = (d.ticker.upper(), d.accession, self._modele())
        if cle in self._mem:
            return self._mem[cle]
        dossier = self._dossier(d.ticker, d.accession)
        chunks = self._chunks_du_depot(vue, d, dossier)
        vecteurs = self._vecteurs(d, chunks, dossier)
        depot = _Depot(
            ticker=d.ticker.upper(),
            accession=d.accession,
            form=d.form,
            cik=d.cik,
            accepted_utc=d.accepted_utc,
            filing_date=d.filing_date,
            report_date=d.report_date,
            primary_document=d.primary_document,
            chunks=chunks,
            vectors=vecteurs,
        )
        self._mem[cle] = depot
        return depot

    # --------------------------------------------------------------------- API publique
    def index_filings(self, ticker: str, as_of: date) -> int:
        """Indexe les dépôts acceptés avant `as_of` ; renvoie le nombre de passages de ces dépôts.
        Idempotent : un second appel n'envoie aucun texte à `embed`."""
        vue, depots = self._eligibles(ticker, as_of)
        return sum(len(self._depot(vue, d).chunks) for d in depots)

    def query(self, ticker: str, question: str, as_of: date, *, k: int = 5) -> RagResult:
        """Les `k` passages les plus proches de `question` parmi les dépôts acceptés avant `as_of`."""
        if k < 1:
            raise ValueError("k doit valoir au moins 1")
        vue, depots = self._eligibles(ticker, as_of)
        indexes = [self._depot(vue, d) for d in depots]
        total = sum(len(x.chunks) for x in indexes)
        replis = [x.accession for x in indexes if x.section_fallback]
        if total == 0:
            return RagResult(
                ticker=ticker.upper(),
                question=question,
                as_of=as_of,
                passages=[],
                n_chunks_indexed=0,
            )
        res = self.llm.embed(
            [self._prefixe("query") + question], date_donnees=as_of, agent="rag_query"
        )
        q = np.asarray(res.vectors[0], dtype=np.float64)
        n = np.linalg.norm(q)
        q = q / n if n else q
        candidats: list[tuple[float, int, int, _Depot]] = []
        for rang, x in enumerate(indexes):  # rang : 0 = dépôt le plus récent
            if not len(x.chunks):
                continue
            if x.vectors.shape[1] != q.shape[0]:
                raise ToolError(
                    f"dimension des vecteurs ({x.vectors.shape[1]}) différente de celle de la "
                    f"question ({q.shape[0]}) : index construit avec un autre modèle ?"
                )
            scores = x.vectors @ q
            candidats += [(float(s), rang, i, x) for i, s in enumerate(scores)]
        candidats.sort(key=lambda t: (-t[0], t[1], t[2]))  # déterministe à score égal
        passages = [self._passage(x, x.chunks[i], s) for s, _, i, x in candidats[:k]]
        return RagResult(
            ticker=ticker.upper(),
            question=question,
            as_of=as_of,
            passages=passages,
            n_chunks_indexed=total,
            section_fallback=bool(replis),
            fallback_accessions=replis,
        )

    # --------------------------------------------------------------------- citation
    @staticmethod
    def _passage(x: _Depot, c: dict[str, Any], score: float) -> Passage:
        texte = c["text"]
        extrait = texte if len(texte) <= 500 else texte[:497].rstrip() + "..."
        periode = x.report_date or x.filing_date
        url = ARCHIVE.format(
            cik=int(x.cik), acc=x.accession.replace("-", ""), doc=x.primary_document or ""
        ).rstrip("/")
        source = Source(
            source_id=f"sec:{x.ticker}:{x.accession}:{section_code(c['section']).replace(' ', '')}:"
            f"{c['n_in_section']}:{c['fp'][:8]}",
            type="depot_sec",
            titre=f"{x.ticker} {x.form} ({periode.isoformat()}), {c['section']}",
            reference=url,
            date_publication=x.accepted_utc.astimezone(UTC),
            extrait=extrait,
        )
        return Passage(
            text=texte,
            section=c["section"],
            score=score,
            source=source,
            section_fallback=c["section_code"] == FALLBACK_SECTION,
        )


__all__ = [
    "FilingsRAG",
    "NoFilingsError",
    "Passage",
    "PROMPTS_DIR",
    "RagQuestion",
    "RagResult",
    "Section",
    "chunk_text",
    "guide_for",
    "load_guide",
    "load_questions",
    "rag_prompt_refs",
    "split_sections",
]
