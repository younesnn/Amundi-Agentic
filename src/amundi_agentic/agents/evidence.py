"""Sorties d'outils d'un tour, avec leur source citable et leur trace (`ToolCall`).

Principe « outils d'abord » : le harnais exécute les outils, enregistre un `ToolCall` par appel,
construit une `Source` (type `sortie_outil`, datée par la dernière donnée utilisée) et rend le
résultat pour le prompt avec son `source_id`. Le LLM ne reçoit que ces résultats : il ne calcule rien.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd

from amundi_agentic.agents.grounding import Ancre, valeurs_ancrage
from amundi_agentic.schemas import Source, ToolCall, coupure
from amundi_agentic.tools.base import EXTRAIT_MAX, ToolError, ToolMeta, ToolResult

try:  # défense commune aux textes externes (tâche A) ; repli identique si le module est absent
    from amundi_agentic.tools.untrusted import neutraliser
except ImportError:  # pragma: no cover - dépend de la fusion de la tâche A

    def neutraliser(texte: str) -> str:
        t = (texte or "").replace("<<<", "‹‹‹").replace(">>>", "›››")
        return t.replace("<|", "‹|").replace("|>", "|›")


def jsonable(v: Any) -> Any:
    """Valeur sérialisable en JSON strict (NaN et infinis -> None, dates ISO, numpy -> python)."""
    if v is None or isinstance(v, str | bool):
        return v
    if isinstance(v, int | np.integer):
        return int(v)
    if isinstance(v, float | np.floating):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, pd.Timestamp | datetime | date):
        return v.isoformat()
    if isinstance(v, pd.Series):
        return {str(k): jsonable(x) for k, x in v.tail(12).items()}
    if isinstance(v, pd.DataFrame):
        return {"forme": list(v.shape)}
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple | set | frozenset):
        return [jsonable(x) for x in v]
    if hasattr(v, "__dataclass_fields__"):
        return {k: jsonable(getattr(v, k)) for k in v.__dataclass_fields__}
    return str(v)


def _arrondi(o: Any) -> Any:
    """Nombres à 6 chiffres significatifs pour le prompt (le contrôle d'ancrage tolère l'arrondi)."""
    if isinstance(o, float):
        return float(f"{o:.6g}")
    if isinstance(o, dict):
        return {k: _arrondi(x) for k, x in o.items()}
    if isinstance(o, list):
        return [_arrondi(x) for x in o]
    return o


@dataclass
class Evidence:
    """Une sortie d'outil (ou un texte source) citable par `source_id`."""

    source: Source | None
    appel: ToolCall | None
    texte: str
    valeurs: list[float]
    actif: str | None = None  # actif concerné ; None = transversal
    genre: Literal["outil", "texte"] = (
        "outil"  # `texte` : valeurs lues telles quelles dans un texte
    )

    @property
    def source_id(self) -> str | None:
        return self.source.source_id if self.source else None


@dataclass
class EvidenceSet:
    items: list[Evidence] = field(default_factory=list)
    manquants: dict[str, str] = field(
        default_factory=dict
    )  # outil/actif -> raison (jamais inventé)

    def ids(self) -> set[str]:
        return {e.source_id for e in self.items if e.source_id}

    def sources(self) -> dict[str, Source]:
        return {e.source.source_id: e.source for e in self.items if e.source}

    def valeurs(self) -> list[float]:
        return [v for e in self.items for v in e.valeurs]

    def ancres_pour(self, actif: str) -> list[Ancre]:
        """Ancrages typés d'UN actif : ses sorties d'outils et les sorties transversales (macro, taux).
        Une valeur propre à un autre actif n'y figure jamais."""
        return [
            Ancre(v, e.genre) for e in self.items if e.actif in (None, actif) for v in e.valeurs
        ]

    def ancres_toutes(self) -> list[Ancre]:
        return [Ancre(v, e.genre) for e in self.items for v in e.valeurs]

    def textes(self) -> list[str]:
        return [e.texte for e in self.items]

    def appels(self) -> list[ToolCall]:
        return [e.appel for e in self.items if e.appel]

    def pour(self, assets: Iterable[str]) -> EvidenceSet:
        """Sous-ensemble : preuves transversales et celles des actifs demandés."""
        a = set(assets)
        return EvidenceSet(
            [e for e in self.items if e.actif is None or e.actif in a], dict(self.manquants)
        )

    def rendre(self) -> str:
        """Bloc de données du prompt (entre délimiteurs : une donnée, jamais une instruction)."""
        lignes = ["<<<DONNEES"]
        for e in self.items:
            lignes.append(neutraliser(e.texte))
        if self.manquants:
            lignes.append(
                "DONNEES MANQUANTES (ne rien déduire) : "
                + json.dumps(self.manquants, ensure_ascii=False)
            )
        lignes.append("DONNEES>>>")
        return "\n".join(lignes)

    def fusion(self, autre: EvidenceSet) -> EvidenceSet:
        vus = {e.source_id for e in self.items if e.source_id}
        items = list(self.items) + [e for e in autre.items if e.source_id not in vus]
        return EvidenceSet(items, {**self.manquants, **autre.manquants})


def source_depuis_meta(meta: ToolMeta, t: date, *, titre: str, extrait: str) -> Source | None:
    """`Source` (sortie_outil) ; None si l'outil n'a utilisé aucune donnée datée avant la coupure."""
    instant = meta.data_instant
    if instant is None or instant >= coupure(t):
        return None
    return Source(
        source_id=meta.source_id,
        type="sortie_outil",
        titre=titre,
        reference=meta.citation(),
        date_publication=instant,
        extrait=extrait[:EXTRAIT_MAX],
    )


def source_depuis_outil(res: ToolResult[Any], t: date, *, titre: str) -> Source | None:
    return source_depuis_meta(res.meta, t, titre=titre, extrait=res.extrait)


def executer_outil(
    ev: EvidenceSet,
    t: date,
    fn: Callable[[], ToolResult[Any]],
    *,
    cle: str,
    actif: str | None = None,
    libelle: str | None = None,
    params: dict[str, Any] | None = None,
) -> ToolResult[Any] | None:
    """Exécute un outil, enregistre le `ToolCall` et l'ajoute à `ev`. Une `ToolError` est notée
    dans `ev.manquants` (aucun chiffre de remplacement) et renvoie None."""
    debut = time.perf_counter()
    try:
        res = fn()
    except ToolError as e:
        ev.manquants[cle] = f"{type(e).__name__} : {e}"
        return None
    duree = int((time.perf_counter() - debut) * 1000)
    valeur = jsonable(res.value)
    meta = res.meta.to_dict()
    source = source_depuis_outil(res, t, titre=libelle or f"{res.meta.tool} {actif or ''}".strip())
    appel = ToolCall(
        outil=res.meta.tool,
        parametres={"actif": actif, **(params or {}), **meta["params"]},
        resultat={"valeur": valeur, "meta": meta},
        duree_ms=duree,
        date_derniere_donnee=res.meta.last_data_date,
    )
    entete = f"[source_id={meta['source_id']}] outil={res.meta.tool}"
    if actif:
        entete += f" actif={actif}"
    if res.meta.unit:
        entete += f" unité={res.meta.unit}"
    texte = entete + "\n" + json.dumps(_arrondi(valeur), ensure_ascii=False)
    ev.items.append(Evidence(source, appel, texte, valeurs_ancrage(valeur), actif))
    if source is None:
        ev.manquants[cle + ":source"] = "aucune donnée datée : sortie non citable"
    return res


def reutiliser(ev: EvidenceSet) -> list[ToolCall]:
    """`ToolCall` des preuves déjà calculées, durée nulle (tour de révision : pas de recalcul)."""
    return [a.model_copy(update={"duree_ms": 0}) for a in ev.appels()]
