"""Socle des agents à vote : outils d'abord, vue structurée, contrôle d'ancrage, rejet motivé.

Déroulé d'un tour (`analyse` ou `revise`) :

1. le harnais exécute les outils de l'agent (`collecter`), un `ToolCall` par appel ;
2. il assemble le prompt (rôle, profil de risque, règles d'ancrage, éventuel tour de débat et rôle
   d'avocat du diable) et injecte les résultats avec leur `source_id` ;
3. un seul appel LLM structuré (`AgentDraft`) ; le LLM ne calcule rien ;
4. validation d'ancrage : sources citées existantes, chiffres retrouvés (voir `grounding.py`) ;
   réponse invalide : nouvelle demande avec la liste des fautes, au plus `grounding.max_retries`
   fois, puis rejet avec motif explicite (journalisé dans `VueRejetee`, l'agent s'abstient).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.evidence import EvidenceSet, Limite, neutraliser, reutiliser
from amundi_agentic.agents.grounding import Ancre, ancres, chiffres_non_ancres
from amundi_agentic.agents.prompts import PromptComposite
from amundi_agentic.llm.types import LLMError, Message, StructuredOutputError
from amundi_agentic.schemas import (
    AgentTurn,
    AppelJournal,
    Decision5,
    Source,
    View,
    VueRejetee,
)

Nature = Literal["analyse", "revision"]


class ViewDraft(BaseModel):
    """Vue telle que le LLM la produit : ni rendement attendu, ni sources complètes (id seulement)."""

    model_config = ConfigDict(extra="ignore")
    actif: str
    direction: Decision5
    confiance: float = Field(ge=0, le=1)
    arguments_pour: list[str] = Field(min_length=1)
    arguments_contre: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class AgentDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vues: list[ViewDraft]
    objection: str | None = None
    objection_source_ids: list[str] = Field(default_factory=list)
    revision_motif: str | None = None


@dataclass
class Portee:
    """Ce qu'une vue sur l'actif A a le droit de citer : chiffres, sources, limites."""

    ancres: dict[
        str, list[Ancre]
    ]  # actif -> ancrages typés (outils de A, transversaux, pairs sur A)
    union: list[Ancre]  # objection et motif de révision (hors actif)
    sources: dict[str, set[str]]  # actif -> source_id citables (A, transversales, pairs sur A)
    limites: list[Limite] = field(default_factory=list)


@dataclass
class AgentResult:
    turn: AgentTurn
    rejets: list[VueRejetee] = field(default_factory=list)

    def vue(self, actif: str) -> View | None:
        return next((v for v in self.turn.vues if v.actif == actif), None)


def decrire_pairs(
    peers: Sequence[AgentTurn], actifs: Sequence[str]
) -> tuple[str, dict[str, Source], dict[str, list[str]]]:
    """Texte des analyses des pairs, leurs sources, et leurs textes PAR ACTIF (ancrage des chiffres).
    Le contenu est neutralisé : un texte ne peut pas forger un délimiteur de bloc."""
    lignes = ["<<<ANALYSES_DES_PAIRS"]
    sources: dict[str, Source] = {}
    textes: dict[str, list[str]] = {}
    for tour in peers:
        for v in tour.vues:
            if v.actif not in actifs:
                continue
            lignes.append(
                f"- {tour.agent} sur {v.actif} : {v.direction.value} (confiance auto-évaluée {v.confiance:.2f})"
            )
            ce = textes.setdefault(v.actif, [])
            for a in v.arguments_pour:
                lignes.append(f"  pour : {neutraliser(a)}")
                ce.append(a)
            for a in v.arguments_contre:
                lignes.append(f"  contre : {neutraliser(a)}")
                ce.append(a)
            for s in v.sources:
                sources[s.source_id] = s
                lignes.append(f"  source {s.source_id} : {neutraliser(s.extrait)}")
                ce.append(s.extrait)
        if tour.objection:
            lignes.append(
                f"- objection de l'avocat du diable ({tour.agent}) : {neutraliser(tour.objection)}"
            )
            textes.setdefault("", []).append(tour.objection)
    lignes.append("ANALYSES_DES_PAIRS>>>")
    return "\n".join(lignes), sources, textes


class LLMAgent(ABC):
    """Agent qui vote : une vue structurée par actif demandé."""

    name: str
    level: Literal["allocation", "titre"]
    prompt_name: str  # fichier de rôle de `agent_prompts/`

    # ----------------------------------------------------------------- à fournir par chaque agent
    @abstractmethod
    def collecter(self, ctx: AgentContext, assets: Sequence[str]) -> EvidenceSet:
        """Exécute les outils de l'agent (jamais le LLM) pour `assets`."""

    def abstention(self, ctx: AgentContext, assets: Sequence[str], ev: EvidenceSet) -> str | None:
        """Motif d'abstention sans appel LLM (ex. aucune news), sinon None."""
        return None

    # ----------------------------------------------------------------- API (L1 3.3)
    def evidence(self, ctx: AgentContext, assets: Sequence[str]) -> EvidenceSet:
        """Sorties d'outils de l'agent pour `assets`, calculées une seule fois par run : un tour de
        révision (sous-ensemble d'actifs) réutilise les résultats du tour 0, sans recalcul."""
        cle = (self.name, self.level)
        faits, ev = ctx.cache.get(cle, (frozenset(), EvidenceSet()))
        manquants = [a for a in assets if a not in faits]
        if manquants:
            ev = ev.fusion(self.collecter(ctx, manquants))
            ctx.cache[cle] = (frozenset(faits | set(manquants)), ev)
        return ev

    def analyse(self, ctx: AgentContext, assets: Sequence[str], *, tour: int = 0) -> AgentResult:
        return self._tour(ctx, assets, tour, peers=(), majorite=None, devil=False)

    def revise(
        self,
        ctx: AgentContext,
        assets: Sequence[str],
        peers: Sequence[AgentTurn],
        majorite: dict[str, int],
        *,
        tour: int,
        devil: bool,
    ) -> AgentResult:
        return self._tour(ctx, assets, tour, peers=peers, majorite=majorite, devil=devil)

    # ----------------------------------------------------------------- mécanique
    def _prompt(self, ctx: AgentContext, tour: int, debat: bool, devil: bool) -> PromptComposite:
        noms = [self.prompt_name, "regles_communes"]
        if debat:
            noms.append("debate_round")
        if devil:
            noms.append("devil")
        lib = ctx.prompts
        return lib.compose(
            *noms,
            variables={
                "date": ctx.t.isoformat(),
                "horizon": str(ctx.settings.debate.horizon_mois),
                "profil": f"{ctx.profil} : {lib.profil(ctx.profil)}",
                "tour": str(tour),
            },
        )

    def _tour(
        self,
        ctx: AgentContext,
        assets: Sequence[str],
        tour: int,
        *,
        peers: Sequence[AgentTurn],
        majorite: dict[str, int] | None,
        devil: bool,
    ) -> AgentResult:
        assets = list(assets)
        ev = self.evidence(ctx, assets).pour(assets)
        appels_outils = reutiliser(ev) if tour > 0 else ev.appels()
        nature: Nature = "revision" if tour > 0 else "analyse"
        motif_abs = self.abstention(ctx, assets, ev)
        if motif_abs is None and not ev.ids():
            motif_abs = (
                "aucune sortie d'outil citable : "
                + json.dumps(ev.manquants, ensure_ascii=False)[
                    : ctx.settings.limites.motif_max_caracteres
                ]
            )
        if motif_abs is not None:
            return self._abstenir(ctx, assets, tour, motif_abs, appels_outils, 0)

        composite = self._prompt(ctx, tour, debat=tour > 0, devil=devil)
        sources = dict(ev.sources())
        par_actif = {a: ev.ancres_pour(a) for a in assets}
        union = ev.ancres_toutes()
        ids_par_actif = {a: ev.pour([a]).ids() for a in assets}
        blocs = [f"Actifs à analyser : {json.dumps(assets, ensure_ascii=False)}", ev.rendre()]
        if tour > 0:
            texte_pairs, src_pairs, txt_pairs = decrire_pairs(
                [p for p in peers if p.agent != self.name], assets
            )
            sources.update(src_pairs)
            # chiffres déjà validés des pairs : ancrés pour l'actif concerné ; l'objection de
            # l'avocat (hors actif) et le motif de révision peuvent citer n'importe lequel
            for a in assets:
                par_actif[a] = [*par_actif[a], *ancres(txt_pairs.get(a, []), "texte")]
            union = [*union, *(x for t in txt_pairs.values() for x in ancres(t, "texte"))]
            # sources des pairs : citables pour l'actif concerné seulement
            for p in peers:
                for v in p.vues:
                    if v.actif in ids_par_actif:
                        ids_par_actif[v.actif] = ids_par_actif[v.actif] | {
                            s.source_id for s in v.sources
                        }
            blocs.append(texte_pairs)
            blocs.append(
                "Position majoritaire du tour précédent (calculée par le système) : "
                + json.dumps(majorite or {}, ensure_ascii=False)
            )
        messages = [
            Message(role="system", content=composite.texte),
            Message(role="user", content="\n\n".join(blocs)),
        ]
        vues, objection, motif_rev, rejets, dernier_appel = self._demander(
            ctx,
            assets,
            tour,
            nature,
            composite,
            messages,
            sources,
            Portee(par_actif, union, ids_par_actif, ev.limites),
            devil,
        )
        role = "avocat_du_diable" if devil and objection else "normal"
        turn = AgentTurn(
            agent=self.name,
            tour=tour,
            role=role,
            vues=vues,
            objection=objection if role == "avocat_du_diable" else None,
            revision_motif=motif_rev,
            appels_outils=appels_outils,
            appel_id=dernier_appel,
        )
        ctx.rejets.extend(rejets)
        return AgentResult(turn, rejets)

    def _abstenir(
        self, ctx: AgentContext, assets: list[str], tour: int, motif: str, appels, nb: int
    ) -> AgentResult:
        rej = [VueRejetee(agent=self.name, tour=tour, actifs=assets, motif=motif, tentatives=1)]
        ctx.rejets.extend(rej)
        turn = AgentTurn(agent=self.name, tour=tour, vues=[], appels_outils=appels)
        return AgentResult(turn, rej)

    def _demander(
        self,
        ctx: AgentContext,
        assets: list[str],
        tour: int,
        nature: Nature,
        composite: PromptComposite,
        messages: list[Message],
        sources: dict[str, Source],
        valeurs: Portee,
        devil: bool,
    ) -> tuple[list[View], str | None, str | None, list[VueRejetee], str | None]:
        cfg = ctx.settings.grounding
        essais = cfg.max_retries + 1
        derniere_faute: dict[str, str] = {a: "aucune réponse" for a in assets}
        faute_objection = None
        valides: dict[str, View] = {}
        objection = motif_rev = None
        dernier_appel: str | None = None
        essai = 0
        for _ in range(essais):
            essai += 1
            try:
                res = ctx.llm.complete_structured(
                    AgentDraft,
                    messages,
                    date_donnees=ctx.t,
                    tier=composite.niveau,
                    agent=self.name,
                    prompt_ref=composite.ref,
                )
            except StructuredOutputError as exc:
                faute = f"sortie non conforme au schéma après nouvelles tentatives : {str(exc)[: ctx.settings.limites.motif_max_caracteres]}"
                derniere_faute = dict.fromkeys(assets, faute)
                break
            except LLMError:
                raise
            ctx.appels.append(
                AppelJournal(
                    agent=self.name,
                    tour=tour,
                    nature=nature,
                    prompt_id=composite.ref.prompt_id,
                    prompt_version=composite.ref.version,
                    prompt_sha256=composite.ref.sha256,
                    messages=[m.model_dump() for m in messages],
                    reponse=res.text,
                    record=res.record,
                )
            )
            dernier_appel = res.record.appel_id
            draft = res.parsed
            assert isinstance(draft, AgentDraft)
            valides, derniere_faute, faute_objection = self._valider(
                ctx, draft, assets, sources, valeurs, devil, tour
            )
            objection = draft.objection if devil and not faute_objection else None
            motif_rev = draft.revision_motif
            if not derniere_faute and not faute_objection:
                break
            fautes = [f"{a} : {m}" for a, m in derniere_faute.items()]
            if faute_objection:
                fautes.append(f"objection : {faute_objection}")
            messages = [
                *messages,
                Message(role="assistant", content=res.text),
                Message(
                    role="user",
                    content=(
                        "Ta réponse est refusée par le contrôle d'ancrage : "
                        + " ; ".join(fautes)
                        + ". Corrige en n'utilisant que les chiffres et les source_id fournis, "
                        "et renvoie uniquement l'objet JSON complet."
                    ),
                ),
            ]
        rejets: list[VueRejetee] = []
        for a, motif in derniere_faute.items():
            rejets.append(
                VueRejetee(agent=self.name, tour=tour, actifs=[a], motif=motif, tentatives=essai)
            )
        if devil and faute_objection:
            rejets.append(
                VueRejetee(
                    agent=self.name,
                    tour=tour,
                    actifs=[],
                    motif="objection : " + faute_objection,
                    tentatives=essai,
                )
            )
            objection = None
        vues = [valides[a] for a in assets if a in valides]
        return vues, objection, motif_rev, rejets, dernier_appel

    def _valider(
        self,
        ctx: AgentContext,
        draft: AgentDraft,
        assets: list[str],
        sources: dict[str, Source],
        valeurs: Portee,
        devil: bool,
        tour: int,
    ) -> tuple[dict[str, View], dict[str, str], str | None]:
        cfg = ctx.settings.grounding
        par_actif_ancres, union = valeurs.ancres, valeurs.union
        fautes: dict[str, str] = {}
        valides: dict[str, View] = {}
        par_actif: dict[str, list[ViewDraft]] = {}
        for v in draft.vues:
            par_actif.setdefault(v.actif, []).append(v)
        for a in assets:
            vs = par_actif.get(a, [])
            if len(vs) != 1:
                fautes[a] = "exactement une vue par actif demandé" if vs else "vue absente"
                continue
            v = vs[0]
            inconnues = [s for s in v.source_ids if s not in valeurs.sources[a]]
            if inconnues:
                fautes[a] = (
                    f"source_id inexistant parmi les sources de cet actif pour ce tour : {inconnues}"
                )
                continue
            nonancres = chiffres_non_ancres(
                [*v.arguments_pour, *v.arguments_contre], par_actif_ancres[a], cfg
            )
            if nonancres:
                fautes[a] = f"chiffres introuvables dans les sorties d'outils : {nonancres}"
                continue
            lim = [x for x in valeurs.limites if x.actif in (None, a)]
            plafonds = [x.plafond_confiance for x in lim if x.plafond_confiance is not None]
            confiance = min(
                [v.confiance, *plafonds]
            )  # une limite de donnée ne gonfle jamais la confiance
            contre = [
                *v.arguments_contre,
                *(x.texte for x in lim if x.texte not in v.arguments_contre),
            ]
            try:
                valides[a] = View(
                    view_id=f"{ctx.run_id}:{self.name}:{a}:t{tour}",
                    actif=a,
                    niveau_decision=self.level,
                    date_analyse=ctx.t,
                    horizon_mois=ctx.settings.debate.horizon_mois,
                    direction=v.direction,
                    rendement_excedentaire_attendu=None,
                    confiance=confiance,
                    arguments_pour=v.arguments_pour,
                    arguments_contre=contre,
                    sources=[sources[s] for s in dict.fromkeys(v.source_ids)],
                    profil_risque=ctx.profil,
                    auteur=self.name,
                    statut="individuelle",
                    run_id=ctx.run_id,
                )
            except ValidationError as exc:
                fautes[a] = (
                    "vue invalide : "
                    + str(exc.errors()[0]["msg"])[: ctx.settings.limites.motif_max_caracteres]
                )
        # un actif non demandé est ignoré : jamais voté, jamais transmis
        faute_obj = None
        if devil:
            if not (draft.objection and draft.objection.strip()):
                faute_obj = "objection obligatoire pour l'avocat du diable"
            elif not draft.objection_source_ids or any(
                s not in sources for s in draft.objection_source_ids
            ):
                faute_obj = "l'objection doit citer des source_id existants"
            elif chiffres_non_ancres([draft.objection], union, cfg):
                faute_obj = "chiffres introuvables dans l'objection : " + str(
                    chiffres_non_ancres([draft.objection], union, cfg)
                )
        if draft.revision_motif:
            nonancres = chiffres_non_ancres([draft.revision_motif], union, cfg)
            if nonancres:
                draft.revision_motif = None  # motif non ancré : non retenu, sans bloquer la vue
        return valides, fautes, faute_obj
