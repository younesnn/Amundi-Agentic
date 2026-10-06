"""Contrôle d'ancrage (EX-O1-04) : aucun chiffre n'est accepté s'il n'est pas retrouvé dans les
sorties d'outils ou les textes sources du tour ; toute source citée doit exister parmi les sources
du tour.

Règles (documentées, H) :

* Sont contrôlés : les nombres avec décimale (`12,3`, `0.05`), les nombres suivis d'une unité
  financière (`%`, `pb`, `$`...), les entiers de plus de 3 chiffres hors années, et les nombres
  ÉCRITS EN LETTRES (français et anglais) quand ils portent une quantité financière : suivis d'une
  unité (« douze pour cent », « twelve percent », « vingt points de base »), composés de plusieurs
  mots-nombres (« vingt et un », « twenty one ») ou décimaux parlés (« douze virgule sept »,
  « twelve point seven »). Un petit entier banal sans unité (« trois analystes », « un risque »,
  « one », « un » comme article) reste accepté. Les entiers nus courts en chiffres (« 3 mois »,
  « 200 jours », « 12-1 ») et les années ne sont pas contrôlés : limite assumée.
* Décimales déguisées : « 12 virgule 7 », « 12 point 7 », « 12 comma 7 », « 12 dot 7 », et les
  séparateurs exotiques (`٫`, `·`, `'`, `’`, espaces fines) sont lus comme des décimales et contrôlés
  comme telles ; les chiffres arabes-indiens et pleine chasse sont ramenés en ASCII.
* Dates (`2024-02-01`, `01/02/2024`) retirées avant la lecture des nombres.
* Tolérance d'arrondi : un chiffre écrit avec d décimales est retrouvé à une demi-unité de sa dernière
  décimale ; un entier, à `min(0,5 ; tolerance_relative_entiers x valeur)` (H, `config/debate.yaml`),
  ce qui ramène les coïncidences accidentelles d'un entier à une fraction de ce qu'elles étaient.
* Échelle selon l'unité, pour les ancrages TYPÉS (`Ancre`) : une sortie d'outil est une fraction ou un
  ratio ; un « % » se compare donc à la valeur x 100, un « pb » à la valeur x 10 000, un nombre sans
  unité à la valeur telle quelle. Une valeur lue dans un texte source (dépôt, news) se compare telle
  quelle. Les ancrages en `float` nu (compatibilité) gardent la comparaison multi-échelles de
  `facteurs_echelle`. Le signe est ignoré.
* Séparateur de milliers ambigu (« 1,234 ») : les deux lectures (1,234 et 1234) sont acceptées.
* Les ancrages viennent des sorties d'outils (récursivement), des textes des sources et des
  chiffres déjà validés des pairs.
"""

from __future__ import annotations

import contextlib
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from amundi_agentic.agents.settings import GroundingCfg

_DATES = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b")
_NOMBRE = re.compile(
    r"(?<![\w.,])[-−–+]?(?:\d{1,3}(?:[   ,.]\d{3})+(?!\d)|\d+)(?:[.,]\d+)?(?!\w)",
    re.UNICODE,
)
_UNITE_SUIVANTE = re.compile(
    r"\s*(%|pb\b|bps\b|\$|€|usd\b|eur\b|millions?\b|milliards?\b|md\b)", re.I
)
_CHIFFRES_EXOTIQUES = str.maketrans(
    {
        **{chr(0x0660 + i): str(i) for i in range(10)},  # chiffres arabes-indiens
        **{chr(0x06F0 + i): str(i) for i in range(10)},  # arabes-indiens étendus
        **{chr(0xFF10 + i): str(i) for i in range(10)},  # pleine chasse
    }
)
_SEPARATEUR_EXOTIQUE = re.compile(r"(?<=\d)[٫·'’ʼ](?=\d)")
_ESPACE_FINE = re.compile(r"(?<=\d)[   ](?=\d{1,2}(?!\d))")
_SEP_PARLE = r"(?:virgule|point|comma|dot)"

# --- nombres en lettres (accents retirés pour la comparaison)
_DIZAINE = 10  # définition de la numération : « vingt » = 2 dizaines, etc.
_MOTS: dict[str, int] = {
    **{
        m: i
        for i, m in enumerate(
            [
                "zero",
                "un",
                "deux",
                "trois",
                "quatre",
                "cinq",
                "six",
                "sept",
                "huit",
                "neuf",
                "dix",
                "onze",
                "douze",
                "treize",
                "quatorze",
                "quinze",
                "seize",
            ]
        )
    },
    "une": 1,
    "vingts": 2 * _DIZAINE,
    **{
        m: i * _DIZAINE
        for i, m in enumerate(
            [
                "vingt",
                "trente",
                "quarante",
                "cinquante",
                "soixante",
                "septante",
                "huitante",
                "nonante",
            ],
            start=2,
        )
    },
    **{
        m: i
        for i, m in enumerate(
            [
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
                "ten",
                "eleven",
                "twelve",
                "thirteen",
                "fourteen",
                "fifteen",
                "sixteen",
                "seventeen",
                "eighteen",
                "nineteen",
            ]
        )
    },
    **{
        m: i * _DIZAINE
        for i, m in enumerate(
            ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"], start=2
        )
    },
}
_MOTS["octante"] = _MOTS["huitante"]
_CENT = {"cent", "cents", "hundred", "hundreds"}
_MAGNITUDES = {
    "mille": 10**3, "thousand": 10**3, "million": 10**6, "millions": 10**6,
    "milliard": 10**9, "milliards": 10**9, "billion": 10**9, "billions": 10**9,
}  # fmt: skip
_CHIFFRES_MOTS = {m for m, v in _MOTS.items() if v < 10 and m not in ("une",)} | {"zero"}
_LIAISONS = {"et", "and"}
_SEP_MOTS = {"virgule", "point", "comma", "dot"}
_UNITE_MOT = re.compile(
    r"\s*(?:de\s+|of\s+)?(?P<u>pour\s*cent|per\s*cent|percent|%|points?\s+de\s+base|basis\s+points?"
    r"|bps\b|pb\b|dollars?|euros?|usd\b|eur\b|\$|€|millions?\b|milliards?\b|billions?\b)",
    re.I,
)
_MAGNITUDE_UNITES = {"million": 10**6, "milliard": 10**9, "billion": 10**9, "md": 10**9}


def _sans_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    )


@dataclass(frozen=True)
class Ancre:
    """Valeur d'ancrage typée : `outil` = fraction ou ratio calculé ; `texte` = telle qu'écrite."""

    valeur: float
    genre: Literal["outil", "texte"] = "outil"


@dataclass(frozen=True)
class Claim:
    """Un chiffre écrit par un agent."""

    brut: str
    valeur: float
    decimales: int
    unite: str
    alternatives: tuple[tuple[float, int], ...] = ()  # autres lectures (séparateur de milliers)
    mot: bool = False  # écrit en lettres ou en décimale parlée


def _candidats(token: str) -> list[tuple[float, int]]:
    """Interprétations numériques (valeur absolue, décimales) d'un jeton brut."""
    t = token.strip().lstrip("-−–+").replace(" ", "").replace(" ", "").replace(" ", "")
    if not t:
        return []
    sorties: list[tuple[float, int]] = []
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        mille = "." if dec == "," else ","
        n = t.replace(mille, "").replace(dec, ".")
        sorties.append((float(n), len(t.split(dec)[-1])))
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        parties = t.split(sep)
        if len(parties) == 2:
            sorties.append((float(parties[0] + "." + parties[1]), len(parties[1])))
        if all(len(p) == 3 for p in parties[1:]) and len(parties[0]) <= 3:
            sorties.append((float("".join(parties)), 0))  # lecture « séparateur de milliers »
        if len(parties) > 2 and not sorties:
            return []
    else:
        sorties.append((float(t), 0))
    return sorties


def _normaliser(texte: str) -> str:
    t = texte.translate(_CHIFFRES_EXOTIQUES)
    t = _SEPARATEUR_EXOTIQUE.sub(",", t)
    t = _ESPACE_FINE.sub(",", t)
    # « 12 virgule 7 », « 12 point 7 » : deux entiers séparés par un mot décimal
    t = re.sub(rf"(?<![\w.,])(\d+)\s+{_SEP_PARLE}\s+(\d+)\b", r"\1,\2", t, flags=re.I)
    chiffres = {m: str(v) for m, v in _MOTS.items() if v < 10 and m != "une"}
    mots = "|".join(sorted(chiffres, key=len, reverse=True))
    t = re.sub(
        rf"(?<![\w.,])(\d+)\s+{_SEP_PARLE}\s+({mots})\b",
        lambda m: f"{m.group(1)},{chiffres[_sans_accents(m.group(2))]}",
        t,
        flags=re.I,
    )
    return t


def _unite(brut: str) -> str:
    u = re.sub(r"\s+", " ", brut.lower())
    if u in ("%", "pour cent", "pourcent", "per cent", "percent"):
        return "%"
    if u.startswith(("point", "basis")) or u in ("bps", "pb"):
        return "pb"
    if u in ("dollar", "dollars", "euro", "euros", "usd", "eur", "$", "€"):
        return "$"
    return u.rstrip("s")  # million, milliard, billion


def _claims_chiffres(t: str, cfg: GroundingCfg) -> list[Claim]:
    claims: list[Claim] = []
    lo, hi = cfg.plage_annees
    unites = {u.lower() for u in cfg.unites_financieres}
    for m in _NOMBRE.finditer(t):
        brut = m.group(0).strip()
        u = _UNITE_SUIVANTE.match(t, m.end())
        unite = _unite(u.group(1)) if u else ""
        if u and u.group(1).lower() not in unites and u.group(1).lower().rstrip("s") not in unites:
            unite = ""
        cands = _candidats(brut)
        if not cands:
            continue
        valeur, dec = cands[0]
        entier_court = dec == 0 and len(re.sub(r"\D", "", brut)) <= 3
        annee = dec == 0 and len(brut) == 4 and lo <= valeur <= hi and not unite
        if (dec == 0 and not unite) and (entier_court or annee):
            continue
        claims.append(Claim(brut, valeur, dec, unite, tuple(cands[1:])))
    return claims


def _valeur_mots(mots: list[str]) -> float:
    """Valeur d'une suite de mots-nombres (français ou anglais), liaisons déjà retirées."""
    total, courant = 0.0, 0.0
    precedent = ""
    for w in mots:
        if w in _MAGNITUDES:
            total += (courant or 1.0) * _MAGNITUDES[w]
            courant = 0.0
        elif w in _CENT:
            courant = (courant or 1.0) * 100
        elif w in ("vingt", "vingts") and precedent == "quatre":
            courant = courant - 4 + 4 * _MOTS["vingt"]  # quatre-vingt(s)
        else:
            courant += _MOTS[w]
        precedent = w
    return total + courant


def _claims_mots(t: str, cfg: GroundingCfg) -> list[Claim]:
    """Nombres écrits en lettres qui expriment une quantité financière (voir en-tête)."""
    claims: list[Claim] = []
    toks = [
        (m.group(0), _sans_accents(m.group(0)), m.start(), m.end())
        for m in re.finditer(r"[^\W\d_]+", t)
    ]
    est_nb = lambda w: w in _MOTS or w in _CENT or w in _MAGNITUDES  # noqa: E731
    i = 0
    while i < len(toks):
        if not est_nb(toks[i][1]):
            i += 1
            continue
        j = i
        mots = [toks[i][1]]
        while j + 1 < len(toks):
            nxt = toks[j + 1][1]
            if est_nb(nxt):
                j += 1
                mots.append(nxt)
            elif nxt in _LIAISONS and j + 2 < len(toks) and est_nb(toks[j + 2][1]):
                j += 2
                mots.append(toks[j][1])
            else:
                break
        fin = toks[j][3]
        valeur = _valeur_mots(mots)
        decimales = 0
        parle = False
        # décimale parlée : « douze virgule sept » (fraction en chiffres-mots ou en nombre)
        if j + 2 < len(toks) and toks[j + 1][1] in _SEP_MOTS and est_nb(toks[j + 2][1]):
            k = j + 2
            chiffres = ""
            while k < len(toks) and toks[k][1] in _CHIFFRES_MOTS:
                chiffres += str(_MOTS[toks[k][1]])
                k += 1
            if not chiffres:
                run = [toks[k][1]]
                while k + 1 < len(toks) and est_nb(toks[k + 1][1]):
                    k += 1
                    run.append(toks[k][1])
                chiffres = str(int(_valeur_mots(run)))
                k += 1
            valeur += float("0." + chiffres)
            decimales = len(chiffres)
            parle = True
            j = k - 1
            fin = toks[j][3]
        u = _UNITE_MOT.match(t, fin)
        unite = _unite(u.group("u")) if u else ""
        composé = sum(1 for w in mots if w not in _LIAISONS) >= 2
        if unite or composé or parle:
            brut = t[toks[i][2] : (u.end() if u else fin)].strip()
            alt: tuple[tuple[float, int], ...] = ()
            if unite in _MAGNITUDE_UNITES:
                alt = ((valeur * _MAGNITUDE_UNITES[unite], decimales),)
            claims.append(Claim(brut, valeur, decimales, unite, alt, mot=True))
        i = j + 1
    return claims


def extraire_chiffres(texte: str, cfg: GroundingCfg) -> list[Claim]:
    """Nombres contrôlés d'un texte, en chiffres ou en lettres (voir règles en tête de module)."""
    t = _DATES.sub(" ", _normaliser(texte))
    return [*_claims_chiffres(t, cfg), *_claims_mots(t, cfg)]


def valeurs_ancrage(objet: Any) -> list[float]:
    """Tous les nombres d'une structure (dict, liste, dataclass, texte), en valeur absolue."""
    sortie: list[float] = []

    def rec(o: Any) -> None:
        if o is None or isinstance(o, bool):
            return
        if isinstance(o, int | float):
            if math.isfinite(float(o)):
                sortie.append(abs(float(o)))
        elif isinstance(o, str):
            for m in _NOMBRE.finditer(_DATES.sub(" ", _normaliser(o))):
                for v, _ in _candidats(m.group(0)):
                    sortie.append(v)
        elif isinstance(o, Mapping):
            for k, v in o.items():
                rec(k)
                rec(v)
        elif isinstance(o, Sequence | set | frozenset) and not isinstance(o, bytes):
            for v in o:
                rec(v)
        elif hasattr(o, "__dataclass_fields__"):
            for k in o.__dataclass_fields__:
                rec(getattr(o, k))
        elif hasattr(o, "item"):  # scalaire numpy
            with contextlib.suppress(TypeError, ValueError):
                rec(o.item())

    rec(objet)
    return sortie


def ancres(objet: Any, genre: Literal["outil", "texte"] = "outil") -> list[Ancre]:
    """`valeurs_ancrage` typées : l'échelle de comparaison dépend de l'unité écrite et du genre."""
    return [Ancre(v, genre) for v in valeurs_ancrage(objet)]


def _tolerance(valeur: float, decimales: int, cfg: GroundingCfg) -> float:
    if decimales > 0:
        base = 0.5 * 10 ** (-decimales)
    else:
        base = min(0.5, cfg.tolerance_relative_entiers * abs(valeur))
    return base * (1 + 1e-9)


def _echelles(a: float | Ancre, claim: Claim, cfg: GroundingCfg) -> list[float]:
    if isinstance(a, Ancre):
        if a.genre == "texte":
            return [1.0]
        if claim.unite == "%":
            return [100.0]
        if claim.unite == "pb":
            return [cfg.facteur_points_de_base]
        return [1.0]
    if claim.unite == "pb":
        return [cfg.facteur_points_de_base, 1.0]
    return list(cfg.facteurs_echelle)


def est_ancre(claim: Claim, valeurs: Iterable[float | Ancre], cfg: GroundingCfg) -> bool:
    """Le chiffre est-il retrouvé parmi les valeurs d'ancrage (tolérance d'arrondi, échelle) ?"""
    lectures = [(claim.valeur, claim.decimales), *claim.alternatives]
    mult = _MAGNITUDE_UNITES.get(claim.unite)
    if mult:
        lectures.append((claim.valeur * mult, claim.decimales))
    for a in valeurs:
        v = abs(a.valeur if isinstance(a, Ancre) else a)
        for k in _echelles(a, claim, cfg):
            for cible, dec in lectures:
                if abs(cible - v * k) <= _tolerance(cible, dec, cfg):
                    return True
    return False


def chiffres_non_ancres(
    textes: Iterable[str], valeurs: Sequence[float | Ancre], cfg: GroundingCfg
) -> list[str]:
    """Chiffres (écrits tels quels) introuvables parmi `valeurs`, dans l'ordre, sans doublon."""
    manquants: list[str] = []
    for texte in textes:
        for c in extraire_chiffres(texte, cfg):
            if not est_ancre(c, valeurs, cfg) and c.brut not in manquants:
                manquants.append(c.brut)
    return manquants
