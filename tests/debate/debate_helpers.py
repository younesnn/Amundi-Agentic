"""Réponses scriptées du LLM simulé pour les tests de débat."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from amundi_agentic.agents.mock_policy import _niveau_vers_direction, politique_simulee

Script = Callable[[str, int, str], int | None]  # (rôle, tour, actif) -> niveau (None : inchangé)


def _role(systeme: str) -> str:
    return systeme.strip().splitlines()[0].removeprefix("# ").strip()


def scripte(script: Script, objection_ok: bool = True):
    """Handler : repart de la politique simulée et impose les niveaux du script."""

    def handler(model: str, messages: list[dict[str, str]]) -> str:
        base = json.loads(politique_simulee(model, messages))
        systeme = next(m["content"] for m in messages if m["role"] == "system")
        if "vues" not in base:
            return json.dumps(base)
        m = re.search(r"Tu es au tour (\d+) du débat", systeme)
        tour = int(m.group(1)) if m else 0
        role = _role(systeme)
        for v in base["vues"]:
            n = script(role, tour, v["actif"])
            if n is not None:
                v["direction"] = _niveau_vers_direction(n)
        if not objection_ok:
            base.pop("objection", None)
        return json.dumps(base, ensure_ascii=False)

    return handler


def appels_par_role(ctx) -> dict[str, int]:
    sortie: dict[str, int] = {}
    for a in ctx.appels:
        sortie[a.agent] = sortie.get(a.agent, 0) + 1
    return sortie
