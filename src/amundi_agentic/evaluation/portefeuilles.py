# ruff: noqa: E501, N806, N818
"""Règles de décision de la réplication (D-065 §4 et §5) : des niveaux du débat aux portefeuilles.

Un seul débat par titre, profil et exécution donne cinq lectures :
* `valuation_seul` et `fundamental_seul` : le vote du tour 0 de chaque agent ;
* `ET` : BUY si les deux agents sont positifs au tour 0 ; `OU` : BUY si l'un d'eux l'est (agrégations
  sans débat, mêmes votes de tour 0) ;
* `multi_agent` : le niveau final du débat.

Mapping : niveau > seuil = BUY, sinon SELL (pas de HOLD). Abstention, rejet d'ancrage ou `voix_unique`
= titre EXCLU des portefeuilles « signal » (`None`), jamais un SELL implicite ; la sensibilité
rapportée est « abstention = BUY » (les abstenus sont inclus ; lire l'abstention comme SELL ne changerait
rien à un portefeuille qui ne contient que des BUY). ET et OU exigent les deux votes (un vote manquant exclut).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

PORTEFEUILLES = ("valuation_seul", "fundamental_seul", "ET", "OU", "multi_agent")
Decision = Literal["BUY", "SELL"] | None

AGENT_VALUATION = "valuation"
AGENT_FUNDAMENTAL = "fundamental"


def _lire(niveau: int | None, seuil: int) -> Decision:
    if niveau is None:
        return None
    return "BUY" if niveau > seuil else "SELL"


def decisions(
    enreg: Mapping[str, Any],
    seuil: int,
    *,
    abstention_sell: bool = False,
    abstention_buy: bool = False,
) -> dict[str, Decision]:
    """Décision de chaque portefeuille pour un titre, depuis l'enregistrement compact d'un débat.

    `enreg["votes_tour0"]` : agent -> niveau au tour 0 (absent si abstention ou rejet) ;
    `enreg["final"]` : {niveau, statut} ou None (aucune vue valide).
    """
    votes = enreg.get("votes_tour0") or {}
    v = votes.get(AGENT_VALUATION)
    f = votes.get(AGENT_FUNDAMENTAL)
    final = enreg.get("final")
    if v is not None and f is not None:
        et: Decision = "BUY" if (v > seuil and f > seuil) else "SELL"
        ou: Decision = "BUY" if (v > seuil or f > seuil) else "SELL"
    else:
        et = ou = None
    multi: Decision = None
    if final is not None and final.get("statut") != "voix_unique":
        multi = _lire(final["niveau"], seuil)
    sortie: dict[str, Decision] = {
        "valuation_seul": _lire(v, seuil),
        "fundamental_seul": _lire(f, seuil),
        "ET": et,
        "OU": ou,
        "multi_agent": multi,
    }
    if abstention_buy:
        sortie = {k: ("BUY" if d is None else d) for k, d in sortie.items()}
    if abstention_sell:
        sortie = {k: ("SELL" if d is None else d) for k, d in sortie.items()}
    return sortie


def titres_buy(
    par_titre: Mapping[str, Mapping[str, Decision]],
    portefeuille: str,
    univers: Mapping[str, Any] | list[str],
) -> list[str]:
    """Titres BUY d'un portefeuille parmi `univers`, dans l'ordre de `univers`."""
    return [t for t in univers if par_titre.get(t, {}).get(portefeuille) == "BUY"]


def compter(
    par_titre: Mapping[str, Mapping[str, Decision]], portefeuille: str, univers: list[str]
) -> dict[str, int]:
    """BUY, SELL et exclus d'un portefeuille parmi `univers` (un titre absent de `par_titre` est exclu)."""
    buy = sell = excl = 0
    for t in univers:
        d = par_titre.get(t, {}).get(portefeuille)
        if d == "BUY":
            buy += 1
        elif d == "SELL":
            sell += 1
        else:
            excl += 1
    return {"BUY": buy, "SELL": sell, "exclus": excl}


def etiquette_decision(d: Decision) -> str:
    return "EXCLU" if d is None else d
