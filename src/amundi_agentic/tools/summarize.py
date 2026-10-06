# ruff: noqa: E501
"""Résumé de news avec réflexion : résumer, critiquer, affiner (AlphaAgents §2.2.3 ; EX-O1-15).

Règles (L1 §4, EX-NF-09, D-023) :
* uniquement des articles publiés STRICTEMENT avant la coupure de t (t 00:00 Europe/Paris) ; pour GDELT,
  `published_at` est la date d'observation (`seendate`), traitée comme date de publication (borne
  prudente) et signalée dans le titre de la source ;
* nombre d'appels LLM = 1 + 2 x `reflection_rounds` (un résumé, puis par tour une critique et un
  affinage) : à utiliser dans le budget de L1 §11.2 ; les nouvelles tentatives sur sortie invalide ne
  sont pas comptées ici (elles figurent dans `LLMClient.records`) ;
* le LLM ne calcule rien : la sortie est refusée (et redemandée par le client) si elle contient un
  chiffre absent des articles montrés, ou une citation d'un article inconnu ;
* texte externe encapsulé entre délimiteurs dans un message utilisateur, jamais dans le message
  système ; les tentatives d'injection détectées sont journalisées (`tools/untrusted.py`).

Limite du contrôle de chiffres : il ne voit que les chiffres écrits en chiffres (pas « trois ») et
accepte un nombre présent dans les articles même s'il est attribué au mauvais objet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Sequence
from datetime import UTC, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from amundi_agentic.data.models import NewsItem
from amundi_agentic.data.pit import cutoff_utc
from amundi_agentic.llm.client import LLMClient
from amundi_agentic.llm.types import Message
from amundi_agentic.schemas import Source
from amundi_agentic.tools.text_config import SummaryConfig, load_text_tools_config, prompt_ref
from amundi_agentic.tools.untrusted import (
    FERMETURE,
    OUVERTURE,
    detect_injection,
    encapsuler,
    signaler,
)

log = logging.getLogger(__name__)

PROMPTS = ("summary_summarize_v1", "summary_critique_v1", "summary_refine_v1")
_CITATIONS = re.compile(r"\[([^\[\]]+)\]\s*$")


class NewsSummary(BaseModel):
    """Résumé sourcé. Chaque point clé se termine par ses citations `[source_id, ...]`, toutes
    présentes dans `sources`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    key_points: list[str]
    sources: list[Source]
    reflection_rounds: int
    n_items: int
    n_calls: int
    # Ajout au contrat du lead (additif, vide par défaut) : « article_id:motif » par injection détectée.
    injection_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _citations_connues(self) -> NewsSummary:
        connus = {s.source_id for s in self.sources}
        for p in self.key_points:
            m = _CITATIONS.search(p)
            ids = [x.strip() for x in m.group(1).split(",")] if m else []
            if not ids:
                raise ValueError(f"point clé sans citation : {p[:60]!r}")
            inconnus = [i for i in ids if i not in connus]
            if inconnus:
                raise ValueError(f"citation inconnue {inconnus} dans le point clé {p[:60]!r}")
        return self


# ------------------------------------------------------------------------------ chiffres
_NOMBRE = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*")


def _canon(s: str) -> str | None:
    try:
        d = Decimal(s).normalize()
    except InvalidOperation:
        return None
    return format(d, "f")


def number_variants(token: str) -> set[str]:
    """Écritures numériques possibles d'un nombre (virgule décimale ou séparateur de milliers)."""
    s = re.sub(r"[   ]", "", token)
    out: set[str] = set()
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        mil = "." if dec == "," else ","
        out.add(s.replace(mil, "").replace(dec, "."))
    elif s.count(",") + s.count(".") == 0:
        out.add(s)
    else:
        sep = "," if "," in s else "."
        if s.count(sep) > 1:
            out.add(s.replace(sep, ""))  # 1,234,567
        else:
            avant, apres = s.split(sep)
            out.add(f"{avant}.{apres}")  # décimal
            if len(apres) == 3:
                out.add(avant + apres)  # milliers
    return {c for c in (_canon(v) for v in out) if c is not None}


def numbers_in(texte: str) -> list[set[str]]:
    """Un ensemble de variantes par nombre écrit en chiffres (les alias `N3` sont ignorés)."""
    sans_alias = re.sub(r"\bN\d+\b", " ", texte)
    return [number_variants(m.group(0)) for m in _NOMBRE.finditer(sans_alias)]


def unsupported_numbers(texte: str, sources: Sequence[str]) -> list[str]:
    """Nombres de `texte` absents de `sources` (tous textes confondus), tels qu'écrits."""
    connus: set[str] = set()
    for src in sources:
        for v in numbers_in(src):
            connus |= v
    manquants = []
    for m in _NOMBRE.finditer(re.sub(r"\bN\d+\b", " ", texte)):
        if not (number_variants(m.group(0)) & connus):
            manquants.append(m.group(0))
    return manquants


# ------------------------------------------------------------------------------ schémas dynamiques
class Critique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problems: list[str]
    missing: list[str]
    verdict: Literal["ok", "a_corriger"]


def _schema_brouillon(alias: Sequence[str], textes_autorises: Sequence[str]):
    """Schéma d'un résumé : citations restreintes aux alias fournis, chiffres vérifiés."""
    citation = Literal[tuple(alias)]  # type: ignore[valid-type]
    point = create_model(
        "KeyPoint",
        __config__=ConfigDict(extra="forbid"),
        text=(str, Field(min_length=1)),
        sources=(list[citation], Field(min_length=1)),  # type: ignore[valid-type]
    )

    def verifier(self):
        texte = self.summary + "\n" + "\n".join(p.text for p in self.key_points)
        manquants = unsupported_numbers(texte, textes_autorises)
        if manquants:
            raise ValueError(
                f"chiffres absents des articles : {manquants} ; reprends-les tels quels ou retire-les"
            )
        return self

    return create_model(
        "Brouillon",
        __config__=ConfigDict(extra="forbid"),
        __validators__={"chiffres": model_validator(mode="after")(verifier)},
        summary=(str, Field(min_length=1)),
        key_points=(list[point], Field(min_length=1)),  # type: ignore[valid-type]
    )


# ------------------------------------------------------------------------------ articles
def _nettoyer(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _empreinte(it: NewsItem) -> str:
    brut = "\x1f".join((it.source, it.title, it.summary, it.url, it.time_semantics))
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def retenir_articles(
    items: Sequence[NewsItem], as_of: date, max_items: int
) -> tuple[list[NewsItem], int]:
    """Articles publiés strictement avant la coupure de `as_of`, sans doublon, du plus récent au plus
    ancien, au plus `max_items`. Renvoie aussi le nombre d'articles écartés pour date >= t.

    Doublons (même `item_id`) : la règle est indépendante de l'ordre d'entrée. On retient la version
    de date de publication la PLUS ANCIENNE connue avant t, puis, à date égale, celle dont l'empreinte
    SHA-256 du contenu (source, titre, résumé, url, sémantique de date) est la plus petite."""
    coupure = cutoff_utc(as_of).to_pydatetime()
    par_id: dict[str, NewsItem] = {}
    futurs = 0
    for it in items:
        if it.published_at.tzinfo is None:
            raise ValueError(f"article {it.item_id} : date de publication sans fuseau")
        if it.time_semantics not in ("published", "seendate"):
            raise ValueError(f"article {it.item_id} : time_semantics inconnu {it.time_semantics!r}")
        if it.published_at >= coupure:
            futurs += 1
            continue
        actuel = par_id.get(it.item_id)
        if actuel is None or (it.published_at, _empreinte(it)) < (
            actuel.published_at,
            _empreinte(actuel),
        ):
            par_id[it.item_id] = it
    gardes = sorted(par_id.values(), key=lambda i: (i.published_at, i.item_id), reverse=True)
    if futurs:
        log.warning(
            "%d article(s) publiés à t ou après écartés du résumé (as_of=%s)", futurs, as_of
        )
    return gardes[:max_items], futurs


def _texte_montre(it: NewsItem, limite: int) -> str:
    t = _nettoyer(it.title)
    r = _nettoyer(it.summary)
    return (t + ("\n" + r if r and r != t else ""))[:limite]


def _source(it: NewsItem, montre: str) -> Source:
    titre = (_nettoyer(it.title) or "(sans titre)")[:200]
    if it.time_semantics == "seendate":
        titre = f"{titre} (date d'observation GDELT)"[:230]
    return Source(
        source_id=f"news:{it.item_id}",
        type="news",
        titre=titre,
        reference=it.url or f"{it.source}:{it.item_id}",
        date_publication=it.published_at.astimezone(UTC),
        extrait=montre[:500] or titre[:500],
    )


def _bloc_articles(articles: list[NewsItem], montres: list[str]) -> str:
    blocs = []
    for n, (it, texte) in enumerate(zip(articles, montres, strict=True), 1):
        meta = f"source : {it.source} ; publié : {it.published_at.astimezone(UTC).isoformat()}"
        blocs.append(encapsuler(f"N{n}", f"{meta}\n{texte}"))
    return "\n".join(blocs)


# ------------------------------------------------------------------------------ outil
def summarize_news(
    llm: LLMClient,
    items: Sequence[NewsItem],
    as_of: date,
    *,
    focus: str,
    reflection_rounds: int = 1,
    tier: str = "light",
    prompts_dir: Path | None = None,
    config: SummaryConfig | None = None,
) -> NewsSummary:
    """Résume `items` (publiés avant `as_of`) avec `reflection_rounds` tours de critique et
    d'affinage. Appels : 1 + 2 x reflection_rounds. Sans article éligible : aucun appel, résumé vide
    qui le dit (l'agent signale une couverture insuffisante)."""
    if reflection_rounds < 0:
        raise ValueError("reflection_rounds doit être >= 0")
    cfg = config or load_text_tools_config().summary
    articles, _ = retenir_articles(items, as_of, cfg.max_items)
    if not articles:
        return NewsSummary(
            summary="Aucun article publié avant la date d'analyse : couverture insuffisante.",
            key_points=[],
            sources=[],
            reflection_rounds=reflection_rounds,
            n_items=0,
            n_calls=0,
        )
    montres = [_texte_montre(it, cfg.max_chars_per_item) for it in articles]
    sources = [_source(it, m) for it, m in zip(articles, montres, strict=True)]
    flags: list[str] = []
    for it in articles:
        motifs = detect_injection(f"{it.title}\n{it.summary}")
        if motifs:
            signaler("summarize_news", it.item_id, motifs)
            flags += [f"{it.item_id}:{x}" for x in motifs]
    alias = [f"N{n}" for n in range(1, len(articles) + 1)]
    par_alias = dict(zip(alias, sources, strict=True))
    # chiffres autorisés : ceux des articles montrés, du thème et de la date d'analyse
    autorises = [*montres, focus, as_of.isoformat()]
    Brouillon = _schema_brouillon(alias, autorises)  # noqa: N806
    (r1, p1), (r2, p2), (r3, p3) = (prompt_ref(n, prompts_dir) for n in PROMPTS)
    bloc = _bloc_articles(articles, montres)
    contexte = (
        f"Date d'analyse t : {as_of.isoformat()} (rien de postérieur n'est connu)\n"
        f"Thème : {encapsuler('theme', focus)}\n\nArticles :\n{bloc}"
    )

    def appel(prompt: str, ref, schema, suite: str = ""):
        utilisateur = contexte + suite
        if utilisateur.count(OUVERTURE) != utilisateur.count(FERMETURE):
            # défense en profondeur : un bloc déséquilibré ne part jamais chez le fournisseur
            raise ValueError("blocs de données déséquilibrés dans le message : appel annulé")
        res = llm.complete_structured(
            schema,
            [
                Message(role="system", content=prompt),
                Message(role="user", content=utilisateur),
            ],
            date_donnees=as_of,
            tier=tier,
            agent="summarize_news",
            prompt_ref=ref,
        )
        return res.parsed

    n_calls = 1
    brouillon = appel(p1, r1, Brouillon)
    for _ in range(reflection_rounds):
        manquants = unsupported_numbers(
            brouillon.summary + "\n" + "\n".join(k.text for k in brouillon.key_points), autorises
        )
        texte_brouillon = json.dumps(brouillon.model_dump(), ensure_ascii=False, sort_keys=True)
        # Le brouillon et la critique viennent du modèle : réinjectés comme des données externes
        # (encapsulés, délimiteurs neutralisés), jamais tels quels (injection de second ordre).
        critique = appel(
            p2,
            r2,
            Critique,
            f"\n\nBrouillon :\n{encapsuler('brouillon', texte_brouillon)}\n\nChiffres non "
            f"retrouvés dans les articles (calculé par le code) : {manquants or 'aucun'}",
        )
        texte_critique = json.dumps(critique.model_dump(), ensure_ascii=False, sort_keys=True)
        brouillon = appel(
            p3,
            r3,
            Brouillon,
            f"\n\nBrouillon :\n{encapsuler('brouillon', texte_brouillon)}\n\nCritique :\n"
            f"{encapsuler('critique', texte_critique)}",
        )
        n_calls += 2

    cites: list[Source] = []
    points: list[str] = []
    for k in brouillon.key_points:
        ids = list(dict.fromkeys(k.sources))
        for a in ids:
            if par_alias[a] not in cites:
                cites.append(par_alias[a])
        points.append(f"{k.text.strip()} [{', '.join(par_alias[a].source_id for a in ids)}]")
    return NewsSummary(
        summary=brouillon.summary.strip(),
        key_points=points,
        sources=cites,
        reflection_rounds=reflection_rounds,
        n_items=len(articles),
        n_calls=n_calls,
        injection_flags=flags,
    )
