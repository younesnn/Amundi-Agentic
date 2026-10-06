"""Agent ESG et conformité : déterministe, droit de veto (L1 §4, §9.4 ; D-035, D-048, EX-O1-10).

Aucune décision n'est prise par le LLM. Les règles sont :

* titres : exclusions normatives de `config/esg.yaml` détectées pour l'émetteur (code SIC EDGAR,
  proxy ; indicateur fournisseur s'il existe) -> veto ; sans donnée connue à t, pas de veto mais
  l'état « inconnu » est signalé (« sans exclusion détectée » n'est pas une preuve, Q-26) ;
* ETF : état de chaque critère à trois valeurs (`determine_par_donnee` si un document de la source
  manuelle D-048 le prouve, `suppose_par_regle` si la méthodologie de l'indice le suppose,
  `inconnu`) ; veto seulement si `esg.etf_criteres_requis` (configuration) cite un critère dont
  l'état n'est pas dans `esg.etf_etats_acceptes` ;
* score ESG : absent (aucun score gratuit, D-035, CT-06 suspendue) : signalé, jamais comblé.

Le LLM (niveau `light`) peut seulement formuler l'explication d'un veto déjà prononcé.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.grounding import valeurs_ancrage
from amundi_agentic.agents.simple_call import appel_ancre
from amundi_agentic.data.analysis import CRITERES, DETERMINE, INCONNU, SUPPOSE
from amundi_agentic.llm.types import Message
from amundi_agentic.schemas import (
    ACTIFS_SANS_VUE,
    EsgAssessment,
    RegleDeclenchee,
    View,
    coupure,
)

LIMITE_SCORE = "score ESG absent : aucune source gratuite (D-035), CT-06 suspendue"
LIMITE_FUTUR = (
    "enregistrement ESG observé à t ou après : ignoré (point-in-time), aucun veto fondé dessus"
)
LIMITE_PREUVE = "« sans exclusion détectée » n'est pas une preuve d'absence d'exposition (Q-26)"


class _Explication(BaseModel):
    model_config = ConfigDict(extra="ignore")
    explication: str


class EsgAgent:
    name = "esg"
    prompt_name = "esg"

    # ----------------------------------------------------------------- règles déterministes
    @staticmethod
    def _connu(ctx: AgentContext, rec):
        """(enregistrement utilisable, était-il postérieur à t ?). Un enregistrement observé à t ou
        après la coupure ne fonde jamais un veto, sauf s'il est EXPLICITEMENT marqué non
        point-in-time par la couche de données (mode de sensibilité) : alors signalé comme tel."""
        if rec is None:
            return None, False
        if rec.observed_at >= coupure(ctx.t):
            mode = getattr(ctx.llm, "mode", "evaluation")
            if not (rec.non_point_in_time and ctx.settings.esg.accepter_non_point_in_time[mode]):
                return None, True
        return rec, False

    def evaluer(
        self, ctx: AgentContext, level: Literal["allocation", "titre"], assets: Sequence[str]
    ) -> dict[str, EsgAssessment]:
        return {a: self._evaluer_un(ctx, level, a) for a in assets}

    def _evaluer_un(self, ctx: AgentContext, level: str, actif: str) -> EsgAssessment:
        if level == "allocation":
            ticker = ctx.data.classes[actif]
            return self._etf(ctx, actif, ticker)
        return self._titre(ctx, actif)

    def _titre(self, ctx: AgentContext, ticker: str) -> EsgAssessment:
        rec, futur = self._connu(ctx, ctx.data.esg(ticker))
        regles = ctx.data.esg_rules()
        limites = [LIMITE_PREUVE]
        if futur:
            limites.append(LIMITE_FUTUR)
        if rec is None:
            return EsgAssessment(
                actif=ticker,
                veto=False,
                point_in_time=True,
                methode="regles_emetteur",
                etats=dict.fromkeys(CRITERES, INCONNU),
                limites=["aucune donnée ESG connue à t pour cet émetteur", LIMITE_SCORE, *limites],
            )
        etats: dict[str, str] = {}
        for c in CRITERES:
            if f"vendor_flag:{c}" in rec.notes:
                etats[c] = DETERMINE
            elif regles.get(c, {}).get("sic_ranges") and "no_sic" not in rec.notes:
                etats[c] = SUPPOSE
            else:
                etats[c] = INCONNU
        motifs = [
            RegleDeclenchee(
                regle="exclusion_normative",
                critere=c,
                detail=(
                    f"{regles.get(c, {}).get('label', c)} : exclusion détectée "
                    f"(base : {rec.exclusion_basis or 'inconnue'})"
                ),
                reference=f"config/esg.yaml normative_exclusions.{c}",
            )
            for c in rec.exclusions
        ]
        if rec.score is None:
            limites.insert(0, LIMITE_SCORE)
        if rec.non_point_in_time:
            limites.append("donnée ESG non point-in-time (collectée après t)")
        return EsgAssessment(
            actif=ticker,
            veto=bool(motifs),
            motifs=motifs,
            score=rec.score,
            fournisseur_score=rec.score_source,
            date_score=rec.observed_at.date() if rec.score is not None else None,
            point_in_time=not rec.non_point_in_time,
            methode="regles_emetteur",
            etats=etats,
            limites=limites,
        )

    def _etf(self, ctx: AgentContext, classe: str, ticker: str) -> EsgAssessment:
        cfg = ctx.settings.esg
        vue = ctx.data.etf_esg()
        rec, futur = self._connu(ctx, ctx.data.esg(ticker))
        preuves = vue.proven_exclusions(ticker) if vue is not None else frozenset()
        supposes = set(rec.exclusions) if rec is not None and rec.exclusion_basis else set()
        etats = {
            c: DETERMINE if c in preuves else SUPPOSE if c in supposes else INCONNU
            for c in CRITERES
        }
        motifs = [
            RegleDeclenchee(
                regle="critere_requis_non_satisfait",
                critere=c,
                detail=(
                    f"critère requis `{c}` à l'état `{etats.get(c, INCONNU)}` : "
                    f"états acceptés {cfg.etf_etats_acceptes}"
                ),
                reference="config/debate.yaml esg.etf_criteres_requis",
            )
            for c in cfg.etf_criteres_requis
            if etats.get(c, INCONNU) not in cfg.etf_etats_acceptes
        ]
        limites = [LIMITE_SCORE, LIMITE_PREUVE]
        if futur:
            limites.append(LIMITE_FUTUR)
        if vue is not None:
            sfdr = vue.sfdr(ticker)
            limites.append(
                f"SFDR : {sfdr} (classe un produit, ce n'est pas un score ESG ; "
                "un article 8 n'implique pas l'exclusion des armes controversées)"
            )
        return EsgAssessment(
            actif=classe,
            veto=bool(motifs),
            motifs=motifs,
            point_in_time=not (rec.non_point_in_time if rec is not None else False),
            methode="indice_etf",
            etats=etats,
            limites=limites,
        )

    # ----------------------------------------------------------------- explication (LLM, light)
    def expliquer(
        self, ctx: AgentContext, evaluations: dict[str, EsgAssessment]
    ) -> dict[str, EsgAssessment]:
        """Ajoute l'explication LLM aux seuls vetos ; le veto lui-même n'est jamais modifié.
        Un texte non ancré est remplacé par l'énumération déterministe des règles."""
        sortie: dict[str, EsgAssessment] = {}
        for a, ev in evaluations.items():
            texte = " ; ".join(m.detail for m in ev.motifs) if ev.veto else None
            if ev.veto and ctx.settings.esg.llm_explique_les_vetos:
                composite = ctx.prompts.compose(self.prompt_name)
                regles = [m.model_dump() for m in ev.motifs]
                parsed, _ = appel_ancre(
                    ctx,
                    agent=self.name,
                    tour=0,
                    nature="explication",
                    composite=composite,
                    messages=[
                        Message(role="system", content=composite.texte),
                        Message(
                            role="user",
                            content=f"Actif : {a}. Règles déclenchées :\n<<<DONNEES\n{regles}\nDONNEES>>>",
                        ),
                    ],
                    schema=_Explication,
                    textes=lambda p: [p.explication],
                    valeurs=valeurs_ancrage(regles),
                )
                if parsed is not None:
                    texte = parsed.explication
            sortie[a] = ev.model_copy(update={"explication": texte})
        return sortie


# ----------------------------------------------------------------------------- application du veto
def actifs_vetoes(evaluations: dict[str, EsgAssessment]) -> frozenset[str]:
    return frozenset(a for a, e in evaluations.items() if e.veto)


def filtrer_univers(assets: Iterable[str], vetoes: frozenset[str]) -> list[str]:
    """Univers autorisé : un actif vetoed n'entre ni dans le débat ni dans une proposition."""
    return [a for a in assets if a not in vetoes and a not in ACTIFS_SANS_VUE]


def appliquer_veto(vues: Iterable[View], vetoes: frozenset[str]) -> list[View]:
    """Ceinture : retire toute vue sur un actif vetoed (aucune vue positive, aucune vue du tout)."""
    return [v for v in vues if v.actif not in vetoes]
