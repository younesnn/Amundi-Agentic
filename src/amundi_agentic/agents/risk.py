"""Agent Risque : alertes calculées en Python (`tools/risk.py`), commentaire du LLM (L1 §4, EX-O1-01).

Le LLM ne peut ni créer, ni modifier, ni retirer une alerte : `RiskAssessment.alertes` est écrit
avant l'appel et n'est jamais relu depuis la réponse du modèle. La correspondance actif -> classe
vient de `config/universe.yaml` (via le fournisseur de données), jamais d'une table codée ici.
L'agent ne vote pas ; il module la confiance (facteur h de L1 §6.4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from amundi_agentic.agents.context import AgentContext
from amundi_agentic.agents.evidence import EvidenceSet, executer_outil, source_depuis_meta
from amundi_agentic.agents.grounding import valeurs_ancrage
from amundi_agentic.agents.simple_call import appel_ancre
from amundi_agentic.llm.types import Message
from amundi_agentic.schemas import NiveauAlerte, RiskAssessment, Source, ToolCall
from amundi_agentic.tools import risk as risk_tools

_NIVEAU_NUM = {"aucune": 0, "moderee": 1, "elevee": 2}


class _Commentaire(BaseModel):
    model_config = ConfigDict(extra="ignore")
    commentaire: str


@dataclass
class RiskResult:
    assessment: RiskAssessment
    appels_outils: list[ToolCall]
    indisponibles: dict[str, str] = field(default_factory=dict)  # actif -> raison (pas d'alerte)
    commentaire_rejete: str | None = None  # motif si le commentaire LLM n'a pas passé l'ancrage

    def alerte(self, actif: str, defaut: NiveauAlerte) -> NiveauAlerte:
        """Alerte de l'actif ; si elle n'est pas calculable, le niveau configuré
        (`confidence.alerte_si_indisponible` : jamais « aucune » par défaut silencieux)."""
        return self.assessment.alertes.get(actif, defaut)


class RiskAgent:
    name = "risque"
    prompt_name = "risk"

    def assess(
        self,
        ctx: AgentContext,
        level: Literal["allocation", "titre"],
        assets: list[str],
        *,
        commenter: bool = True,
    ) -> RiskResult:
        cfg = ctx.settings.risk
        modele = (
            risk_tools.RiskThresholds()
        )  # types des champs seulement, valeurs lues dans le YAML
        th = risk_tools.RiskThresholds.from_mapping(
            {
                k: int(v) if isinstance(getattr(modele, k, None), int) else v
                for k, v in cfg.seuils.items()
            }
        )
        series: dict[str, pd.Series] = {}
        cle_actif: dict[str, str] = {}  # clé de série (ticker) -> actif de la décision
        for a in assets:
            if level == "allocation":
                tk = ctx.data.classes[a]
                series[tk] = ctx.data.class_prices(a)
            else:
                tk = a
                series[tk] = ctx.data.stock_prices(a)
            cle_actif[tk] = a
        reference = ctx.data.class_prices(cfg.regime_reference_class)
        vix = ctx.data.macro_series([cfg.vix_series])[0].get(cfg.vix_series)

        ev = EvidenceSet()
        alertes_ticker: dict[str, str] = {}
        indispo: dict[str, str] = {}
        indicateurs: dict[str, float] = {}
        seuils: dict[str, float] = {}
        regime: str | None = None
        sources: dict[str, Source] = {}
        premier = True
        for tk, s in series.items():
            res = executer_outil(
                ev,
                ctx.t,
                lambda tk=tk, s=s, premier=premier: risk_tools.risk_report(
                    pd.DataFrame({tk: s}),
                    reference,
                    ctx.t,
                    th,
                    previous_regime=None,
                    vix=vix if premier else None,
                    replay_weeks=cfg.default_replay_weeks,
                ),
                cle=f"risk_report:{tk}",
                actif=cle_actif[tk],
                libelle=f"Alertes de risque : {cle_actif[tk]}",
            )
            if res is None:
                indispo[tk] = ev.manquants.get(f"risk_report:{tk}", "outil en erreur")
                continue
            rep = res.value
            alertes_ticker.update(rep.alertes)
            indispo.update({a: r for a, r in rep.indisponibles.items() if not a.startswith("__")})
            indicateurs.update(rep.indicateurs)
            seuils = rep.seuils
            if premier:
                regime = rep.regime_volatilite
                if rep.alerte_marche is not None:
                    indicateurs["alerte_marche_vix"] = float(_NIVEAU_NUM[rep.alerte_marche])
                premier = False
            for m in rep.sources:
                src = source_depuis_meta(
                    m, ctx.t, titre=f"Risque : {m.series or 'marché'}", extrait=m.citation()
                )
                if src:
                    sources[src.source_id] = src

        if level == "allocation":
            classes = {tk: cle_actif[tk] for tk in series}
            par_classe = risk_tools.aggregate_alerts_by_class(
                {k: v for k, v in alertes_ticker.items() if k in classes},
                classes,
                [k for k in indispo if k in classes],
            )
            alertes = {c: ca.alerte for c, ca in par_classe.items() if ca.alerte is not None}
        else:
            alertes = {cle_actif[tk]: lvl for tk, lvl in alertes_ticker.items() if tk in cle_actif}
        indispo_actifs = {cle_actif[k]: r for k, r in indispo.items() if k in cle_actif}

        assessment = RiskAssessment(
            date_analyse=ctx.t,
            alertes=alertes,  # type: ignore[arg-type]
            regime_volatilite=regime,  # type: ignore[arg-type]
            indicateurs={k: float(v) for k, v in indicateurs.items()},
            seuils=seuils,
            commentaire="",
            sources=list(sources.values()),
        )
        resultat = RiskResult(assessment, ev.appels(), indispo_actifs)
        if commenter:
            self._commenter(ctx, resultat)
        return resultat

    def _commenter(self, ctx: AgentContext, r: RiskResult) -> None:
        composite = ctx.prompts.compose(self.prompt_name)
        donnees = {
            "alertes": r.assessment.alertes,
            "regime_volatilite": r.assessment.regime_volatilite,
            "indicateurs": {k: float(f"{v:.6g}") for k, v in r.assessment.indicateurs.items()},
            "seuils": r.assessment.seuils,
            "actifs_sans_alerte_calculable": r.indisponibles,
        }
        user = (
            f"Date d'analyse : {ctx.t.isoformat()}. Profil du client : {ctx.profil}.\n"
            "Alertes calculées par le système (non modifiables) :\n<<<DONNEES\n"
            + json.dumps(donnees, ensure_ascii=False)
            + "\nDONNEES>>>"
        )
        parsed, motif = appel_ancre(
            ctx,
            agent=self.name,
            tour=0,
            nature="commentaire",
            composite=composite,
            messages=[
                Message(role="system", content=composite.texte),
                Message(role="user", content=user),
            ],
            schema=_Commentaire,
            textes=lambda p: [p.commentaire],
            valeurs=valeurs_ancrage(donnees),
        )
        if parsed is not None:
            r.assessment = r.assessment.model_copy(update={"commentaire": parsed.commentaire})
        else:
            r.commentaire_rejete = motif
