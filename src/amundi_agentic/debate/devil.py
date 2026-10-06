"""Avocat du diable tournant (L1 §6.3, EX-O1-08).

Au tour r >= 1, l'avocat est le votant d'indice `(r - 1 + h) mod K`, où h est dérivé du hash de
(date, niveau de décision, graine de rotation) : la rotation est reproductible et ne désigne pas
toujours le même agent au premier tour. Son vote compte normalement : aucun appel supplémentaire.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date


def decalage(t: date, niveau: str, graine: int, k: int) -> int:
    """h dans [0, K[ : dérivé du hash de (date, niveau, graine)."""
    if k <= 0:
        raise ValueError("au moins un votant")
    h = hashlib.sha256(f"{t.isoformat()}|{niveau}|{graine}".encode()).hexdigest()
    return int(h[:8], 16) % k


def designer(votants: Sequence[str], tour: int, t: date, niveau: str, graine: int) -> str:
    """Nom de l'avocat du diable du tour `tour` (>= 1) parmi les votants (ordre du round robin)."""
    if tour < 1:
        raise ValueError("pas d'avocat du diable au tour 0 (collaboration)")
    k = len(votants)
    return votants[(tour - 1 + decalage(t, niveau, graine, k)) % k]
