"""Masquage des secrets dans tout texte qui sort du module (journaux, erreurs, cache)."""

from __future__ import annotations

import os
import re

MASQUE = "[CLE_MASQUEE]"

_MOTIFS_SIMPLES = [
    re.compile(r"AIza[0-9A-Za-z_\-]{16,}"),
    re.compile(r"gsk_[0-9A-Za-z]{16,}"),
    re.compile(r"sk-[0-9A-Za-z_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[0-9A-Za-z._\-]{8,}"),
]
# key=..., api_key: ..., "authorization": "..." : le nom est conservé, la valeur masquée.
_MOTIF_AFFECTATION = re.compile(
    r"(?i)((?:api[_-]?key|key|token|authorization)[\"']?\s*[=:]\s*[\"']?)[^&\s\"',}]{6,}"
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
    for motif in _MOTIFS_SIMPLES:
        s = motif.sub(MASQUE, s)
    return _MOTIF_AFFECTATION.sub(lambda m: m.group(1) + MASQUE, s)
