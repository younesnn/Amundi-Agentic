"""Revue indépendante : aucune donnée à t ou après n'entre dans un prompt, une `View` ou un
`ToolCall`. Méthode : un fournisseur HOSTILE sert, en plus des données légitimes, des données de
futur piégées (valeurs énormes, publications tardives, dépôts postérieurs, ESG observé après t) ;
les prompts et sorties d'outils doivent être IDENTIQUES à ceux d'un run sur données propres."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from agents_helpers import T, fabrique_ctx

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.fundamental import FundamentalAgent
from amundi_agentic.agents.macro import MacroAgent
from amundi_agentic.agents.ports import (
    FakeNewsSummary,
    FakeNewsSummaryTool,
    FakePassage,
    FakeRagTool,
)
from amundi_agentic.agents.providers import SyntheticData, rag_synthetique
from amundi_agentic.agents.risk import RiskAgent
from amundi_agentic.agents.sentiment import SentimentAgent
from amundi_agentic.agents.valuation import ValuationAgent
from amundi_agentic.data.models import EsgRecord, NewsItem, NewsQuery
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.schemas import Source, coupure

MARQUEUR = 987654321.0  # valeur de futur : ne doit apparaître nulle part
CLASSES = ["actions_etats_unis", "souverain_euro", "or"]
UTC0 = datetime(T.year, T.month, T.day, tzinfo=UTC)


class DonneesHostiles(SyntheticData):
    """SyntheticData qui NE filtre PAS le futur et y ajoute des pièges."""

    def _avant_t(self, ticker):
        s = self._serie(ticker)
        propre = s[s.index < pd.Timestamp(self.t)]
        piege = pd.Series(
            MARQUEUR,
            index=pd.bdate_range(start=pd.Timestamp(self.t), periods=5),  # la barre de t et après
        )
        piege.name = propre.name  # même nom de série : l'identifiant de source reste comparable
        return pd.concat([propre, piege]).sort_index().rename(propre.name)

    def _macro(self, sid):
        propre = super()._macro(sid)
        pieges = pd.DataFrame(
            {
                # date passée mais publiée APRÈS t (retard de publication) : fuite classique
                "date": [pd.Timestamp(self.t) - pd.Timedelta(days=10)] * 2
                + [pd.Timestamp(self.t) + pd.Timedelta(days=3)],
                "value": [MARQUEUR] * 3,
                "available_from": [
                    pd.Timestamp(self.t) + pd.Timedelta(days=20),
                    pd.Timestamp(self.t),  # disponible exactement à t : pas avant t
                    pd.Timestamp(self.t) + pd.Timedelta(days=4),
                ],
            }
        )
        # le filtre PIT du fournisseur propre a déjà été appliqué à `propre` : on rend aussi les pièges
        return pd.concat([propre, pieges], ignore_index=True)

    def risk_free_annual(self):
        """Taux sans risque calculé sur la série PROPRE : ce test vise les agents, pas ce chemin
        du fournisseur synthétique (qui lit `date` et non `available_from`)."""
        from amundi_agentic.tools.base import ToolResult, make_meta

        df = SyntheticData._macro(self, "fred:DGS1MO")
        d = df[df["date"] < pd.Timestamp(self.t)]
        return ToolResult(
            float(d["value"].iloc[-1]) / 100.0,
            make_meta("risk_free_annual", self.t, d["date"].iloc[-1:], 1, series="fred:DGS1MO"),
        )

    def news(self, query: NewsQuery):
        propres = super().news(query)
        pieges = [
            NewsItem(
                item_id=f"futur-{k}",
                source="hostile",
                published_at=pub,
                title=f"FUITE-NEWS-{k}",
                summary=f"gain de {MARQUEUR}",
                url=f"https://exemple.invalid/futur/{k}",
                tags=query.tags or ("marche",),
            )
            for k, pub in enumerate(
                [
                    UTC0 + timedelta(days=2),  # après t
                    UTC0,  # à t (UTC) : après la coupure de Paris
                    UTC0
                    - timedelta(minutes=30),  # t-1 23:30 UTC = t 00:30 Paris : après la coupure
                ]
            )
        ]
        return [*propres, *pieges]

    def xbrl_facts(self, ticker):
        df = super().xbrl_facts(ticker)
        futur = df.copy()
        futur["filed"] = pd.Timestamp(self.t) + pd.Timedelta(days=5)
        futur["end"] = pd.Timestamp(self.t) + pd.Timedelta(days=1)
        futur["value"] = MARQUEUR
        jour_t = df.copy()
        jour_t["filed"] = pd.Timestamp(self.t)
        jour_t["value"] = MARQUEUR + 1
        return pd.concat([df, futur, jour_t], ignore_index=True)


class RagHostile(FakeRagTool):
    def query(self, ticker, question, as_of, *, k=5):
        res = super().query(ticker, question, as_of, k=k)
        futur = FakePassage(
            text=f"FUITE-RAG chiffre d'affaires de {MARQUEUR:.0f}",
            section="Item 7",
            score=9.9,
            source=Source(
                source_id=f"depot_sec:{ticker}:10-K:futur",
                type="depot_sec",
                titre="10-K futur",
                reference="x",
                date_publication=UTC0 + timedelta(days=30),
                extrait=f"FUITE-RAG {MARQUEUR:.0f}",
            ),
        )
        return type(res)((futur, *res.passages))


class ResumeHostile(FakeNewsSummaryTool):
    def __call__(self, llm, items, as_of, **kw):
        res = super().__call__(llm, items, as_of, **kw)
        futur = Source(
            source_id="news:futur",
            type="news",
            titre="FUITE-RESUME",
            reference="x",
            date_publication=UTC0 + timedelta(days=3),
            extrait=f"FUITE-RESUME {MARQUEUR:.0f}",
        )
        return FakeNewsSummary(res.summary, res.key_points, (*res.sources, futur), 0)


def contexte(tmp_path, hostile):
    ctx = fabrique_ctx(tmp_path)
    if hostile:
        ctx.data = DonneesHostiles(T, stocks=("AAA", "BBB", "CCC"))
        ctx.rag = RagHostile(passages=rag_synthetique(T, ("AAA", "BBB", "CCC")).passages)
        ctx.summarizer = ResumeHostile()
    else:
        ctx.rag = rag_synthetique(T, ("AAA", "BBB", "CCC"))
    return ctx


def tout_executer(ctx):
    """Tous les agents sur les deux niveaux ; renvoie les tours."""
    tours = []
    for ag, actifs in (
        (MacroAgent(), CLASSES),
        (ValuationAgent("allocation"), CLASSES),
        (SentimentAgent("allocation"), CLASSES),
        (FundamentalAgent(), ["AAA"]),
        (SentimentAgent("titre"), ["AAA"]),
        (ValuationAgent("titre"), ["AAA"]),
    ):
        tours.append(ag.analyse(ctx, actifs).turn)
    risque = RiskAgent().assess(ctx, "allocation", CLASSES, commenter=False)
    return tours, risque


def _sans_duree(appels):
    return [{"outil": a.outil, "parametres": a.parametres, "resultat": a.resultat} for a in appels]


def test_prompts_et_sorties_d_outils_identiques_avec_et_sans_donnees_de_futur(tmp_path):
    propre, hostile = contexte(tmp_path / "p", False), contexte(tmp_path / "h", True)
    tp, rp = tout_executer(propre)
    th, rh = tout_executer(hostile)
    assert len(propre.appels) == len(hostile.appels) > 0
    for ap, ah in zip(propre.appels, hostile.appels, strict=True):
        assert ap.messages == ah.messages, f"fuite dans le prompt de {ap.agent}"
    for a, b in zip(tp, th, strict=True):
        assert _sans_duree(a.appels_outils) == _sans_duree(b.appels_outils), a.agent
        assert [v.model_dump() for v in a.vues] == [v.model_dump() for v in b.vues]
    assert rp.assessment.alertes == rh.assessment.alertes
    assert rp.assessment.indicateurs == rh.assessment.indicateurs


def test_aucune_trace_du_futur_dans_les_prompts_les_vues_et_les_toolcalls(tmp_path):
    ctx = contexte(tmp_path, True)
    tours, risque = tout_executer(ctx)
    corpus = json.dumps(
        [a.messages for a in ctx.appels]
        + [[v.model_dump(mode="json") for v in t.vues] for t in tours]
        + [[c.model_dump(mode="json") for c in t.appels_outils] for t in tours]
        + [risque.assessment.model_dump(mode="json")],
        ensure_ascii=False,
        default=str,
    )
    for piege in ("FUITE-NEWS", "FUITE-RAG", "FUITE-RESUME", "987654321", "9.87654321"):
        assert piege not in corpus, piege


def test_sources_et_dates_de_toute_vue_anterieures_a_la_coupure(tmp_path):
    ctx = contexte(tmp_path, True)
    tours, _ = tout_executer(ctx)
    limite = coupure(T)
    vues = [v for t in tours for v in t.vues]
    assert vues
    for v in vues:
        assert v.date_analyse == T  # View.date_analyse = t
        assert v.sources and all(s.date_publication < limite for s in v.sources)
    for t in tours:
        for c in t.appels_outils:
            if c.date_derniere_donnee is not None:
                assert c.date_derniere_donnee < T, (t.agent, c.outil)


def test_la_barre_du_jour_t_et_les_publications_tardives_sont_ecartees_par_les_outils(tmp_path):
    ctx = contexte(tmp_path, True)
    ev = ValuationAgent("allocation").evidence(ctx, CLASSES)
    assert MARQUEUR not in ev.valeurs() and all(abs(v - MARQUEUR) > 1 for v in ev.valeurs())
    macro = MacroAgent().evidence(ctx, CLASSES)
    assert all(abs(v - MARQUEUR) > 1 for v in macro.valeurs())


@pytest.mark.parametrize("decalage_minutes", [-30, 0, 60, 24 * 60])
def test_une_actualite_publiee_apres_la_coupure_de_paris_n_atteint_pas_le_resume(
    tmp_path, decalage_minutes
):
    """Coupure = t 00:00 Europe/Paris = t-1 23:00 UTC (hiver) : -30 min UTC est déjà après."""
    ctx = fabrique_ctx(tmp_path)
    pub = UTC0 + timedelta(minutes=decalage_minutes)

    class Un(SyntheticData):
        def news(self, query):
            return [
                NewsItem(
                    item_id="piege",
                    source="h",
                    published_at=pub,
                    title="PIEGE",
                    summary="x",
                    url="https://exemple.invalid/p",
                    tags=("marche",),
                )
            ]

    ctx.data = Un(T)
    ev = SentimentAgent("allocation").evidence(ctx, ["actions_etats_unis"])
    assert not ev.ids() and "aucune actualité" in json.dumps(ev.manquants, ensure_ascii=False)
    assert ctx.summarizer.appels == []  # l'outil de résumé n'a même pas été appelé


def test_une_actualite_publiee_une_seconde_avant_la_coupure_est_conservee(tmp_path):
    ctx = fabrique_ctx(tmp_path)
    avant = coupure(T) - timedelta(seconds=1)

    class Un(SyntheticData):
        def news(self, query):
            return [
                NewsItem(
                    item_id="ok",
                    source="h",
                    published_at=avant,
                    title="OK",
                    summary="x",
                    url="https://exemple.invalid/ok",
                    tags=("marche",),
                )
            ]

    ctx.data = Un(T)
    ev = SentimentAgent("allocation").evidence(ctx, ["actions_etats_unis"])
    assert ev.ids() and ctx.summarizer.appels[0]["n_items"] == 1


def test_un_depot_sec_et_un_passage_du_futur_sont_ecartes(tmp_path):
    ctx = contexte(tmp_path, True)
    ev = FundamentalAgent().evidence(ctx, ["AAA"])
    texte = ev.rendre()
    assert "FUITE-RAG" not in texte and "987654321" not in texte
    assert not any("futur" in i for i in ev.ids())
    assert all(abs(v - MARQUEUR) > 1 and abs(v - MARQUEUR - 1) > 1 for v in ev.valeurs())


def test_changement_d_heure_la_coupure_suit_europe_paris(tmp_path):
    # t = 2024-03-31 (passage à l'heure d'été) : coupure = 2024-03-30 23:00 UTC ; t+1 : 22:00 UTC
    assert coupure(date(2024, 3, 31)) == datetime(2024, 3, 30, 23, 0, tzinfo=UTC)
    assert coupure(date(2024, 4, 1)) == datetime(2024, 3, 31, 22, 0, tzinfo=UTC)
    assert coupure(date(2024, 10, 27)) == datetime(2024, 10, 26, 22, 0, tzinfo=UTC)
    assert coupure(date(2024, 10, 28)) == datetime(2024, 10, 28, 0, 0, tzinfo=UTC) - timedelta(
        hours=1
    )


def test_un_debat_complet_sur_donnees_hostiles_ne_produit_aucune_source_posterieure(tmp_path):
    ctx = contexte(tmp_path, True)
    votants = construire_votants(ctx, "allocation", live=True)
    esg = EsgAgent().evaluer(ctx, "allocation", CLASSES)
    res = run_debate(
        ctx, "allocation", CLASSES, votants, Coordinator(), esg, risk_agent=RiskAgent()
    )
    limite = coupure(T)
    assert res.vues_finales
    for v in res.vues_finales:
        assert v.date_analyse == T and all(s.date_publication < limite for s in v.sources)
    corpus = res.log.model_dump_json()
    for piege in ("FUITE-", "987654321"):
        assert piege not in corpus
    for a in res.log.appels:
        assert "FUITE-" not in json.dumps(a.messages) and "987654321" not in json.dumps(a.messages)


def test_une_vue_dont_une_source_est_postérieure_est_rejetee_meme_si_l_outil_la_sert(tmp_path):
    """Dernière ceinture : si un outil laissait passer une source datée >= t, la `View` est
    refusée par son validateur (EX-O1-03) au lieu d'être transmise."""
    from amundi_agentic.agents.evidence import EvidenceSet

    class SourceTardive(ValuationAgent):
        def collecter(self, ctx, assets):
            ev = super().collecter(ctx, assets)
            item = ev.items[0]
            tard = item.source.model_copy(update={"date_publication": UTC0 + timedelta(days=1)})
            ev.items[0] = type(item)(tard, item.appel, item.texte, item.valeurs, item.actif)
            return ev

    del EvidenceSet
    ctx = fabrique_ctx(tmp_path)
    r = SourceTardive("allocation").analyse(ctx, [CLASSES[0]])
    assert r.turn.vues == []
    assert any("coupure" in x.motif or "invalide" in x.motif for x in r.rejets)


def test_esg_observe_apres_t_ne_declenche_pas_de_veto(tmp_path):
    """Un enregistrement ESG daté après t ne doit pas fonder un veto (information du futur)."""

    class EsgFutur(SyntheticData):
        def esg(self, asset_id):
            return EsgRecord(
                asset_id=asset_id,
                score=None,
                score_source=None,
                exclusions=("tobacco",),
                exclusion_basis="sic",
                observed_at=UTC0 + timedelta(days=30),
                non_point_in_time=False,
                notes=(),
            )

    ctx = fabrique_ctx(tmp_path)
    ctx.data = EsgFutur(T)
    ev = EsgAgent().evaluer(ctx, "titre", ["AAA"])
    assert ev["AAA"].veto is False


def test_pit_data_provider_et_synthetic_data_ont_la_meme_interface():
    from amundi_agentic.agents.ports import DataProvider
    from amundi_agentic.agents.providers import PitDataProvider

    publics = {n for n in dir(DataProvider) if not n.startswith("_")}
    for classe in (PitDataProvider, SyntheticData):
        assert publics <= {n for n in dir(classe)}, classe.__name__
