"""Politique de réponse du LLM simulé (`--mock`, tests d'intégration) : déterministe, sans réseau.

Elle lit le prompt reçu (titre du rôle, actifs demandés, `source_id` présents) et renvoie un JSON
valide : positions pseudo-aléatoires reproductibles au tour 0, convergence d'un cran vers la
position majoritaire aux tours de débat, objection sourcée pour l'avocat du diable. Aucun chiffre
n'est écrit : le contrôle d'ancrage passe sans rien inventer. Ce n'est PAS une simulation de
marché : elle sert à exercer la mécanique (tours, consensus, journaux), pas à produire des vues.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SRC = re.compile(r"\[source_id=([^\]]+)\]([^\n]*)")


def _h(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _niveau_vers_direction(n: int) -> str:
    return {
        -2: "FORTEMENT_NEGATIF",
        -1: "NEGATIF",
        0: "NEUTRE",
        1: "POSITIF",
        2: "FORTEMENT_POSITIF",
    }[max(-2, min(2, n))]


def politique_simulee(model: str, messages: list[dict[str, str]]) -> str:
    systeme = next((m["content"] for m in messages if m["role"] == "system"), "")
    utilisateur = "\n".join(m["content"] for m in messages if m["role"] == "user")
    titre = systeme.strip().splitlines()[0] if systeme.strip() else ""
    if "Coordinateur : rapport" in systeme:
        return json.dumps(
            {
                "indicateurs_positifs": ["Les analyses citent des résultats d'outils concordants."],
                "preoccupations": ["Certaines positions divergent entre les analystes."],
                "conclusion": "Conclusion simulée, adaptée au profil du client.",
            },
            ensure_ascii=False,
        )
    if "Coordinateur : arbitrage" in systeme:
        lots = re.findall(r"actif=(\S+) min=(-?\d+) max=(-?\d+)", utilisateur)
        return json.dumps(
            {
                "arbitrages": [
                    {
                        "actif": a,
                        "niveau": (int(lo) + int(hi)) // 2,
                        "justification": "Arbitrage simulé : position médiane.",
                    }
                    for a, lo, hi in lots
                ]
            }
        )
    if "Agent Risque" in systeme:
        return json.dumps({"commentaire": "Commentaire simulé des alertes calculées."})
    if "Agent ESG" in systeme:
        return json.dumps({"explication": "Veto motivé par les règles déclenchées."})

    m = re.search(r"Actifs à analyser : (\[.*?\])", utilisateur)
    actifs: list[str] = json.loads(m.group(1)) if m else []
    sources: dict[str | None, str] = {}
    premiere = None
    for sid, reste in _SRC.findall(utilisateur):
        premiere = premiere or sid
        a = re.search(r"actif=(\S+)", reste)
        sources.setdefault(a.group(1) if a else None, sid)
    majorite: dict[str, int] = {}
    mm = re.search(r"Position majoritaire du tour précédent[^\n]*: (\{.*\})", utilisateur)
    if mm:
        majorite = json.loads(mm.group(1))
    debat = "Tour de débat" in systeme or "Tour de débat" in utilisateur
    vues: list[dict[str, Any]] = []
    for a in actifs:
        n = (_h(titre, a) % 3) - 1
        if debat and a in majorite:
            n = n + (1 if majorite[a] > n else -1 if majorite[a] < n else 0)
        sid = sources.get(a) or sources.get(None) or premiere or "inconnu"
        vues.append(
            {
                "actif": a,
                "direction": _niveau_vers_direction(n),
                "confiance": 0.5,
                "arguments_pour": ["Argument favorable tiré des résultats d'outils fournis."],
                "arguments_contre": ["Argument défavorable tiré des résultats d'outils fournis."],
                "source_ids": [sid],
            }
        )
    sortie: dict[str, Any] = {"vues": vues}
    if debat:
        sortie["revision_motif"] = "Position révisée à la lumière des analyses des pairs."
    if "avocat du diable" in systeme.lower():
        sortie["objection"] = "Objection simulée à la position majoritaire."
        sortie["objection_source_ids"] = [premiere or "inconnu"]
    return json.dumps(sortie, ensure_ascii=False)
