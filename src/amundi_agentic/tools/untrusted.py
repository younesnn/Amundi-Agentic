# ruff: noqa: E501
"""Texte externe (news, dépôts SEC) : encapsulation et détection d'injection (EX-NF-09, R-09).

Défense de base, volontairement simple :
* le texte externe est placé entre délimiteurs, dans un message utilisateur, jamais dans le
  message système ; les délimiteurs présents DANS le texte sont neutralisés ;
* les consignes de rôle disent que le contenu délimité est une donnée, jamais une instruction ;
* les motifs d'injection les plus courants sont détectés et journalisés (logger de sécurité).
La détection n'est PAS une garantie : un texte hostile reformulé passe (limite documentée).
"""

from __future__ import annotations

import logging
import re

security_log = logging.getLogger("amundi_agentic.security")

OUVERTURE = "<<<DONNEE"
FERMETURE = "<<<FIN_DONNEE>>>"

# (nom du motif, expression) ; insensible à la casse, français et anglais.
_MOTIFS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (nom, re.compile(expr, re.IGNORECASE))
    for nom, expr in (
        (
            "ignorer_instructions",
            r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|"
            r"all|any|your)\b[^.\n]{0,30}\b(instructions?|rules?|prompts?|guidelines?)\b",
        ),
        (
            "ignorer_instructions_fr",
            r"\b(ignore[zr]?|oublie[zr]?|n['’]?tiens? pas compte)\b[^.\n]{0,40}\b(instructions?|"
            r"consignes?|r[eè]gles?|pr[eé]c[eé]dent\w*)\b",
        ),
        (
            "nouveau_role",
            r"\b(you are now|from now on you|act as|pretend to be|tu es maintenant)\b",
        ),
        (
            "nouvelles_instructions",
            r"\b(new instructions?|nouvelles? (instructions?|consignes?)|system prompt|"
            r"prompt syst[eè]me)\b",
        ),
        (
            "balise_de_role",
            r"(^|\n)\s*(system|assistant|developer)\s*:|<\|(im_start|im_end|system)\|>|\[/?INST\]",
        ),
        (
            "ordre_de_sortie",
            r"\b(respond|answer|reply|output|r[eé]ponds?)\b[^.\n]{0,30}\b(only|exactly|uniquement)\b"
            r"[^.\n]{0,30}\b(buy|sell|strong|achat|vente|json)\b",
        ),
        ("delimiteur_interne", r"<<<\s*(DONNEE|FIN_DONNEE)"),
    )
)


def detect_injection(texte: str) -> list[str]:
    """Noms des motifs d'injection trouvés dans `texte` (liste vide : rien de détecté)."""
    return [nom for nom, motif in _MOTIFS if motif.search(texte or "")]


def neutraliser(texte: str) -> str:
    """Retire du texte externe tout ce qui pourrait imiter un délimiteur ou une balise de rôle."""
    t = (texte or "").replace("<<<", "‹‹‹").replace(">>>", "›››")
    t = t.replace("<|", "‹|").replace("|>", "|›")
    return t


def encapsuler(label: str, texte: str) -> str:
    """Bloc délimité : `<<<DONNEE label>>> … <<<FIN_DONNEE>>>`. `label` est fourni par le code."""
    if not re.fullmatch(r"[A-Za-z0-9_.:\-]+", label):
        raise ValueError(f"label de délimiteur invalide : {label!r}")
    return f"{OUVERTURE} {label}>>>\n{neutraliser(texte)}\n{FERMETURE}"


def signaler(contexte: str, identifiant: str, motifs: list[str]) -> None:
    """Journalise une tentative d'injection (jamais le texte intégral)."""
    security_log.warning(
        "tentative d'injection détectée : contexte=%s id=%s motifs=%s",
        contexte,
        identifiant,
        ",".join(motifs),
    )
