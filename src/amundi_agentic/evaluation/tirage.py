# ruff: noqa: E501, N806, N818
"""Tirage des titres de la réplication (D-021, D-065 §3) : déterministe et vérifiable.

* Le hash de la graine est consigné dans le pré-enregistrement AVANT le tirage ; le tirage vérifie
  que la graine du protocole correspond à ce hash.
* La « permutation fixée d'avance » est le tri des titres par SHA-256(graine | étiquette | titre) :
  indépendant de la version de numpy, reproductible sur toute machine, sans état.
* Remplacement : le titre suivant dans la permutation, seulement sur échec technique (données ou
  fournisseur). Jamais sur une abstention, une décision ou une performance.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

DOMAINE_GRAINE = "amundi-agentic/replication/graine/v1"


class GraineNonConforme(ValueError):
    """La graine du protocole ne correspond pas au hash enregistré avant le tirage."""


def graine_sha256(graine: int) -> str:
    """Empreinte de la graine, à consigner avant tout tirage (le tirage la révèle ensuite)."""
    return hashlib.sha256(f"{DOMAINE_GRAINE}|{graine}".encode()).hexdigest()


def verifier_graine(graine: int, sha256_enregistre: str) -> None:
    if graine_sha256(graine) != sha256_enregistre:
        raise GraineNonConforme(
            "la graine du protocole ne correspond pas au hash enregistré avant le tirage "
            "(déviation : créer une nouvelle version du pré-enregistrement)"
        )


def _cle(graine: int, etiquette: str, ticker: str) -> str:
    return hashlib.sha256(f"{graine}|{etiquette}|{ticker}".encode()).hexdigest()


def permutation(tickers: Iterable[str], graine: int, etiquette: str = "primaire") -> list[str]:
    """Permutation déterministe : tri par (SHA-256(graine|étiquette|titre), titre)."""
    return sorted(set(tickers), key=lambda tk: (_cle(graine, etiquette, tk), tk))


@dataclass(frozen=True)
class Tirage:
    permutation: tuple[str, ...]  # tous les titres utilisables, dans l'ordre de la permutation
    titres: tuple[str, ...]  # titre hors pool (en tête) puis les n retenus
    retenus: tuple[str, ...]  # les n titres tirés dans le pool
    remplaces: dict[str, str] = field(default_factory=dict)  # titre en échec -> remplaçant
    insuffisant: bool = False  # moins de n titres admissibles


def tirage_primaire(
    utilisables: Sequence[str],
    *,
    hors_pool: str,
    n: int,
    graine: int,
    echecs: Mapping[str, str] | None = None,
) -> Tirage:
    """Les n premiers titres admissibles de la permutation, plus le titre hors pool.

    `echecs` : titres à écarter pour échec technique (valeur : motif, publié par l'appelant).
    """
    echecs = echecs or {}
    perm = permutation([t for t in utilisables if t != hors_pool], graine, "primaire")
    retenus: list[str] = []
    for tk in perm:
        if len(retenus) == n:
            break
        if tk not in echecs:
            retenus.append(tk)
    nominaux = perm[:n]
    en_echec = [t for t in nominaux if t in echecs]
    remplacants = [t for t in retenus if t not in nominaux]
    remplaces = dict(zip(en_echec, remplacants, strict=False))
    return Tirage(
        tuple(perm),
        (hors_pool, *retenus),
        tuple(retenus),
        remplaces,
        insuffisant=len(retenus) < n,
    )


def tirages_secondaires(
    admissibles: Sequence[str], *, hors_pool: str, n: int, graine: int, nombre: int
) -> list[tuple[str, ...]]:
    """`nombre` tirages de n titres parmi les admissibles (déjà évalués), hors titre hors pool.
    Aucun appel LLM : ce sont des sous-ensembles du pool évalué. Chaque tirage est une permutation
    indépendante (étiquette `secondaire|k`)."""
    pool = sorted({t for t in admissibles if t != hors_pool})
    sortie: list[tuple[str, ...]] = []
    for k in range(nombre):
        perm = sorted(pool, key=lambda tk, k=k: (_cle(graine, f"secondaire|{k}", tk), tk))
        sortie.append(tuple(perm[:n]))
    return sortie
