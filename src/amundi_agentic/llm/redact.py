"""Masquage des secrets dans tout texte qui sort du module (journaux, erreurs, cache)."""

from __future__ import annotations

import os
import re

MASQUE = "[CLE_MASQUEE]"

# En-tête Authorization : toute la valeur est masquée, quel que soit le schéma (Bearer, Basic,
# Digest avec paramètres entre guillemets, jeton nu). Forme JSON ("authorization": "..."),
# jusqu'au guillemet fermant (échappements compris) ; forme texte, jusqu'à la fin de ligne.
_MOTIF_AUTORISATION_JSON = re.compile(r"""(?i)(authorization["']\s*[:=]\s*["'])(?:[^"'\\]|\\.)*""")
_MOTIF_AUTORISATION = re.compile(r"(?i)(authorization\s*[=:]\s*)[^\n]+")
_MOTIFS_SIMPLES = [
    re.compile(r"AIza[0-9A-Za-z_\-]{16,}"),
    re.compile(r"gsk_[0-9A-Za-z]{16,}"),
    re.compile(r"sk-[0-9A-Za-z_\-]{16,}"),
    re.compile(r"(?i)\bbearer\s+\S{6,}"),
]
# key=..., api_key: ..., "authorization": "..." : le nom est conservé, la valeur masquée.
_MOTIF_AFFECTATION = re.compile(
    r"(?i)((?:api[_-]?key|key|token)[\"']?\s*[=:]\s*[\"']?)[^&\s\"',}]{6,}"
)


def _secrets_de_l_environnement() -> list[str]:
    return [
        valeur
        for nom, valeur in os.environ.items()
        if valeur and len(valeur) >= 8 and nom.endswith(("_KEY", "_TOKEN", "_SECRET"))
    ]


def redact(texte: object, secrets: list[str] | None = None) -> str:
    """Remplace les valeurs de secrets connues (variables d'environnement `*_KEY`, `*_TOKEN`,
    `*_SECRET`, plus `secrets`) et les motifs de clés usuels par un masque."""
    s = str(texte)
    valeurs = {*(secrets or []), *_secrets_de_l_environnement()}
    for v in sorted(valeurs, key=len, reverse=True):
        s = s.replace(v, MASQUE)
    s = _MOTIF_AUTORISATION_JSON.sub(lambda m: m.group(1) + MASQUE, s)
    s = _MOTIF_AUTORISATION.sub(lambda m: m.group(1) + MASQUE, s)
    for motif in _MOTIFS_SIMPLES:
        s = motif.sub(MASQUE, s)
    return _MOTIF_AFFECTATION.sub(lambda m: m.group(1) + MASQUE, s)
