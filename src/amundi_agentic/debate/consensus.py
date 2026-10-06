"""Consensus et confiance, calculés en Python (L1 §6.2 et §6.4, D-015, D-016).

Aucune fonction ici n'appelle un LLM et aucun nombre d'hypothèse (H) n'est codé : seuils, facteurs
g, h, rho, c_max et c_min viennent de `config/debate.yaml` (`agents/settings.py`). La confiance
auto-déclarée de chaque agent n'entre pas dans le calcul.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from amundi_agentic.agents.settings import ConfidenceCfg, ConsensusCfg

Statut = Literal["unanime", "consensus", "contestee", "voix_unique"]


@dataclass(frozen=True)
class Etat:
    """Situation d'un actif après un tour, à partir des seuls niveaux structurés."""

    niveaux: tuple[int, ...]
    unanime: bool
    ecart: int
    mediane: int  # arrondie vers 0 (K pair)


def mediane_vers_zero(niveaux: Sequence[int]) -> int:
    """Médiane des niveaux ; pour un nombre pair de votes, moyenne des deux centraux tronquée
    vers 0 (L1 §6.1 : « la médiane de deux niveaux étant arrondie vers 0 »)."""
    if not niveaux:
        raise ValueError("aucun vote")
    t = sorted(niveaux)
    n = len(t)
    if n % 2:
        return t[n // 2]
    return int((t[n // 2 - 1] + t[n // 2]) / 2)


def evaluer(niveaux: Sequence[int]) -> Etat:
    if not niveaux:
        raise ValueError("aucun vote")
    ecart = max(niveaux) - min(niveaux)
    return Etat(tuple(niveaux), ecart == 0, ecart, mediane_vers_zero(niveaux))


def statut_apres_rmax(e: Etat, cfg: ConsensusCfg) -> Statut:
    """Statut quand le nombre maximal de tours est atteint sans unanimité (L1 §6.2)."""
    if e.unanime:
        return "unanime"
    if e.ecart >= cfg.ecart_contestee_min:
        return "contestee"
    if e.ecart <= cfg.ecart_consensus_large:
        return "consensus"
    raise ValueError(
        "écart non couvert par la configuration du consensus"
    )  # exclu par la validation


def borner(n: int, bas: int, haut: int, borne_contestee: int) -> int:
    """Niveau d'une vue contestée : dans [min, max] des votes, puis dans [-borne, +borne]."""
    n = max(bas, min(haut, n))
    return max(-borne_contestee, min(borne_contestee, n))


def accord(niveaux: Sequence[int], n_final: int) -> float:
    """A = 1 - (1/K) sum |n_k - n*| / 4, dans [0, 1] (L1 §6.4)."""
    k = len(niveaux)
    return 1.0 - sum(abs(n - n_final) for n in niveaux) / (4.0 * k)


def confiance(
    a: float, statut: Statut, tours_utilises: int, alerte: str, cfg: ConfidenceCfg
) -> float:
    """c = clip(c_max . A . g . rho . h) entre c_min et c_max (L1 §6.4)."""
    if statut == "voix_unique":
        # un agent seul ne porte jamais la confiance d'un consensus : plafond configuré (H)
        return min(cfg.plafond_voix_unique, confiance(a, "unanime", tours_utilises, alerte, cfg))
    g = cfg.g[statut]
    rho = max(0.0, 1.0 - cfg.rho_par_tour * tours_utilises)
    h = cfg.h[alerte]
    brut = cfg.c_max * a * g * rho * h
    return min(cfg.c_max, max(cfg.c_min, brut))
