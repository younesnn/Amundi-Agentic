# ruff: noqa: E501
"""Revue indépendante de la réplication : non-fuite (risque n°1) autour des décisions et de la mesure.

Aucun réseau, aucune clé, aucun appel Ollama : `MockLLMClient` et données synthétiques.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from amundi_agentic.agents.mock_policy import politique_simulee
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.data.models import LookAheadError, NewsItem
from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.evaluation import perf as perf_mod
from amundi_agentic.evaluation.repl_config import ConfigReplicationError, charger_config
from amundi_agentic.evaluation.replication import Etat, produire_decisions
from amundi_agentic.evaluation.sources import (
    GardeFuture,
    SourceReelle,
    SourceSynthetique,
    etat_pool,
)
from amundi_agentic.llm import MockLLMClient, load_config

T = date(2024, 2, 1)
SURCHARGE = {
    "tirage": {"n_titres": 3, "n_tirages_secondaires": 10},
    "inference": {"bootstrap": {"n_reechantillonnages": 100}},
    "executions": [{"nom": "baseline", "temperature": 0.0, "paraphrase": None, "graine_llm": 0}],
}


# ============================================================ GardeFuture : matrice adverse
class Inner:
    """Fournisseur factice : chaque méthode renvoie ce que le test lui fait renvoyer."""

    def __init__(self, **retours):
        self.__dict__.update(retours)
        self.view = "VUE-BRUTE"  # attribut non appelable (comme PitDataProvider.view)

    def servir(self, valeur):
        return valeur


def _g(valeur):
    return GardeFuture(Inner(), T).servir  # pragma: no cover


def garde_sur(valeur):
    g = GardeFuture(Inner(), T)
    return g.servir(valeur)


FUTURS = {
    "serie_a_t": pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-31", "2024-02-01"])),
    "serie_apres_t": pd.Series([1.0], index=pd.to_datetime(["2024-03-15"])),
    "df_index_a_t": pd.DataFrame({"x": [1]}, index=pd.to_datetime(["2024-02-01"])),
    "df_date_a_t": pd.DataFrame({"date": pd.to_datetime(["2024-02-01"]), "value": [1.0]}),
    "df_available_from_a_t": pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02"]), "available_from": pd.to_datetime(["2024-02-01"])}
    ),
    "df_filed_apres_t": pd.DataFrame({"filed": pd.to_datetime(["2024-02-05"])}),
    "dict_imbrique": {"a": [pd.Series([1.0], index=pd.to_datetime(["2024-02-02"]))]},
    "tuple_imbrique": (1, {"k": pd.DataFrame({"date": pd.to_datetime(["2025-01-01"])})}),
    "news_a_minuit_utc": NewsItem("n1", "s", datetime(2024, 2, 1, tzinfo=UTC), "t", "", "u"),
    "news_apres": NewsItem("n2", "s", datetime(2024, 5, 1, tzinfo=UTC), "t", "", "u"),
    "liste_de_news": [NewsItem("n3", "s", datetime(2024, 3, 1, tzinfo=UTC), "t", "", "u")],
}
PASSENT = {
    "serie_veille": pd.Series([1.0], index=pd.to_datetime(["2024-01-31"])),
    "df_veille": pd.DataFrame({"date": pd.to_datetime(["2024-01-31"]), "value": [1.0]}),
    "news_t_moins_1us": NewsItem(
        "n4", "s", datetime(2024, 1, 31, 23, 59, 59, 999999, tzinfo=UTC), "t", "", "u"
    ),
    "vide": pd.Series(dtype=float),
}


@pytest.mark.parametrize("nom", sorted(FUTURS))
def test_garde_refuse_toute_donnee_a_t_ou_apres(nom):
    with pytest.raises(LookAheadError):
        garde_sur(FUTURS[nom])


@pytest.mark.parametrize("nom", sorted(PASSENT))
def test_garde_laisse_passer_le_strictement_anterieur(nom):
    garde_sur(PASSENT[nom])


def test_garde_compte_ses_controles_et_note_la_date_max():
    g = GardeFuture(Inner(), T)
    g.servir(PASSENT["serie_veille"])
    assert g.n_controles == 1 and g.date_max_servie == pd.Timestamp("2024-01-31")


def test_garde_bornes_hors_perimetre_documentees_ce_qu_elle_ne_voit_pas():
    """LIMITES (non bloquantes, la couche de données filtre déjà) : la garde ne contrôle que les
    objets pandas, les dates de colonnes `date`/`available_from`/`filed`, les news et les fiches ESG.
    Un attribut non appelable (`view`), un objet `Filing` (accepted_utc) ou un passage RAG
    (date_publication) datés après t ne sont PAS vus par la garde."""

    class Depot:
        accepted_utc = datetime(2024, 3, 1, tzinfo=UTC)

    class Passage:
        date_publication = datetime(2024, 3, 1, tzinfo=UTC)

    garde_sur(Depot())
    garde_sur([Depot(), Passage()])
    g = GardeFuture(Inner(), T)
    assert (
        g.view == "VUE-BRUTE"
    )  # contournement : la vue brute sort sans contrôle (le RAG s'en sert)
    df_autre_col = pd.DataFrame({"end": pd.to_datetime(["2025-01-01"]), "v": [1]})
    garde_sur(df_autre_col)  # colonne `end` non inspectée


def test_garde_plus_laxiste_d_une_heure_que_la_coupure_de_paris_documente():
    """Pour les news, la garde compare à minuit UTC de t ; la couche de données coupe à minuit de
    Paris (23:00 UTC la veille en hiver). Une news à 23:30 UTC la veille de t passe la garde mais
    est déjà écartée par la couche : la garde ne remplace pas la couche (ceinture seulement)."""
    n = NewsItem("n5", "s", datetime(2024, 1, 31, 23, 30, tzinfo=UTC), "t", "", "u")
    garde_sur(n)


# ============================================================ mondes synthétiques
def _monde():
    cfg = charger_config(overrides=SURCHARGE)
    src = SourceSynthetique(cfg, n_pool=8, sans_donnees=2)
    ep = etat_pool(src, cfg)
    llm_cfg = load_config()
    captures: list[list[dict]] = []

    def handler(model, messages):
        captures.append(messages)
        return politique_simulee(model, messages)

    def fab(ex, *, cache_dir):
        return MockLLMClient(
            llm_cfg, handler=handler, mode="interactif", run_id=f"r-{ex.nom}", seed=0
        )

    return cfg, src, ep, fab, captures


def test_prompts_et_messages_ne_contiennent_aucune_date_posterieure_a_t_ni_le_calendrier_de_suivi(
    tmp_path,
):
    cfg, src, ep, fab, captures = _monde()
    etat = Etat(tmp_path / "e.json", cfg.source_sha256 or "")
    produire_decisions(
        cfg,
        src,
        ep,
        load_settings(),
        etat,
        fab,
        executions=["baseline"],
        univers="primaire",
        dossier_cache=None,
    )
    assert captures
    texte = "\n".join(m["content"] for msgs in captures for m in msgs)
    dates = set(re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", texte))
    futures = sorted(
        "-".join(d) for d in dates if "-".join(d) > "2024-01-31" and "-".join(d) != "2024-02-01"
    )
    assert futures == [], futures
    for interdit in (
        str(cfg.cible.fin_suivi),
        str(cfg.cible.as_of_performance),
        "fin_suivi",
        "as_of_performance",
        "2024-05",
        "mai 2024",
        "31 mai",
    ):
        assert interdit not in texte, interdit


def test_journaux_calls_jsonl_date_donnees_toujours_t(tmp_path):
    cfg, src, ep, fab, _ = _monde()
    vus = []
    original = fab

    def fab2(ex, *, cache_dir):
        c = original(ex, cache_dir=cache_dir)
        vus.append(c)
        return c

    etat = Etat(tmp_path / "e.json", cfg.source_sha256 or "")
    produire_decisions(
        cfg,
        src,
        ep,
        load_settings(),
        etat,
        fab2,
        executions=["baseline"],
        univers="primaire",
        dossier_cache=None,
    )
    dates = {str(r.date_donnees) for c in vus for r in c.records}
    assert dates <= {"2024-02-01"}, dates


def _interdit(nom):
    def f(*a, **k):
        raise AssertionError(nom)

    return f


def test_aucun_prix_ni_taux_de_suivi_lu_pendant_les_decisions_et_perf_jamais_appelee(
    tmp_path, monkeypatch
):
    cfg, src, ep, fab, _ = _monde()
    lus: list[str] = []
    monkeypatch.setattr(src, "prix_suivi", lambda *a, **k: lus.append("prix"))
    monkeypatch.setattr(src, "taux_suivi", lambda *a, **k: lus.append("taux"))
    for nom in (
        "mesurer",
        "valeur_portefeuille",
        "fenetre_suivi",
        "taux_quotidiens",
        "taux_moyen",
        "rendements",
        "prix_relatifs",
    ):
        monkeypatch.setattr(perf_mod, nom, _interdit(nom))
    etat = Etat(tmp_path / "e.json", cfg.source_sha256 or "")
    produire_decisions(
        cfg,
        src,
        ep,
        load_settings(),
        etat,
        fab,
        executions=["baseline"],
        univers="pool",
        dossier_cache=None,
    )
    assert lus == [] and etat.debats


def test_prix_hostiles_apres_t_ne_changent_pas_les_decisions(tmp_path):
    """Deux mondes identiques avant t, radicalement différents après t : mêmes décisions."""
    cfg, src, ep, fab, _ = _monde()
    cfg2, src2, ep2, fab2, _ = _monde()
    orig = src2.fournisseur_decision

    def hostile(titres, t):
        g = orig(titres, t)
        for tk in titres:
            s = g._inner._serie(tk).copy()
            s[s.index >= pd.Timestamp(t)] *= 1e6  # le futur explose
            g._inner._prix[tk] = s
        return g

    src2.fournisseur_decision = hostile  # type: ignore[method-assign]
    e1 = Etat(tmp_path / "a.json", cfg.source_sha256 or "")
    e2 = Etat(tmp_path / "b.json", cfg.source_sha256 or "")
    for c, s, ep_, fb, e in ((cfg, src, ep, fab, e1), (cfg2, src2, ep2, fab2, e2)):
        produire_decisions(
            c,
            s,
            ep_,
            load_settings(),
            e,
            fb,
            executions=["baseline"],
            univers="pool",
            dossier_cache=None,
        )

    def vue(e):
        return {k: (d["votes_tour0"], d["final"]) for k, d in e.debats.items()}

    assert vue(e1) == vue(e2)


# ============================================================ éligibilité : lit-elle l'après-t ?
class _Vue:
    def __init__(self, series, filings):
        self._s, self._f = series, filings

    def prices(self, tickers, start=None, field="adj_close"):
        for t in tickers:
            if t not in self._s:
                raise KeyError(t)
        return pd.DataFrame({t: self._s[t] for t in tickers})

    def filings(self, ticker, forms):
        return list(self._f)


class _Pit:
    def __init__(self, series, filings):
        self._v = _Vue(series, filings)

    def as_of(self, t):
        return self._v


def _source_reelle(series):
    s = SourceReelle.__new__(SourceReelle)
    s._pit = _Pit(series, [object()])
    s._modal = None
    s._comptes = {}
    s.pool = lambda: sorted(series)  # type: ignore[method-assign]
    return s


def _serie(debut="2023-01-02", fin="2024-05-31", trous=()):
    idx = pd.bdate_range(debut, fin)
    s = pd.Series(100.0, index=idx)
    return s.drop(pd.to_datetime(list(trous))) if trous else s


def test_eligibilite_de_base_utilisable():
    cfg = charger_config()
    src = _source_reelle({"A": _serie(), "B": _serie(), "C": _serie()})
    assert src.eligibilite("A", cfg) == (True, "utilisable")


@pytest.mark.xfail(
    strict=True,
    reason="BLOQUANT (revue) : `sources.py` `_compte_suivi` et `eligibilite` (suivi_complet_requis) "
    "lisent les prix POSTÉRIEURS à t (séances entre t et fin_suivi) pour exclure un titre du pool : "
    "un titre radié, suspendu ou absorbé après t est écarté a posteriori, ce qui dépend du futur "
    "(biais du survivant corrélé à la performance). Aucune VALEUR n'est lue, mais la disponibilité "
    "après t décide de l'univers. Correction : retirer la règle ou la fonder sur des données < t.",
)
def test_eligibilite_ne_depend_d_aucune_donnee_posterieure_a_t():
    cfg = charger_config()
    trous = ["2024-03-14", "2024-03-15", "2024-04-02"]  # séances manquantes APRÈS t
    ref = _source_reelle({"A": _serie(), "B": _serie(), "C": _serie()})
    futur_altere = _source_reelle({"A": _serie(), "B": _serie(trous=trous), "C": _serie()})
    assert ref.eligibilite("B", cfg) == futur_altere.eligibilite("B", cfg)


def test_eligibilite_n_utilise_que_des_comptes_et_des_dates_pas_des_valeurs():
    """Ce qui est vrai : deux séries de mêmes dates et de valeurs opposées après t donnent la même
    éligibilité (aucune valeur de cours postérieure n'est lue)."""
    cfg = charger_config()
    a = _serie()
    b = a.copy()
    b[b.index >= pd.Timestamp(T)] = [
        100.0 * (1 + 0.01 * i) for i in range((b.index >= pd.Timestamp(T)).sum())
    ]
    c = a.copy()
    c[c.index >= pd.Timestamp(T)] = [
        100.0 / (1 + 0.01 * i) for i in range((c.index >= pd.Timestamp(T)).sum())
    ]
    r1 = _source_reelle({"A": b, "B": a, "C": a}).eligibilite("A", cfg)
    r2 = _source_reelle({"A": c, "B": a, "C": a}).eligibilite("A", cfg)
    assert r1 == r2 == (True, "utilisable")


def test_eligibilite_historique_et_janvier_ne_comptent_que_les_seances_avant_t():
    cfg = charger_config()
    court = _serie(debut="2023-06-01")  # ~165 séances avant t < 252
    ok, motif = _source_reelle({"A": court, "B": _serie(), "C": _serie()}).eligibilite("A", cfg)
    assert not ok and "historique insuffisant" in motif
    # beaucoup de barres APRÈS t ne rattrapent pas un historique court
    assert "avant t" in motif


# ============================================================ taux sans risque : date de publication
def _store_taux(tmp_path, points):
    store = ParquetStore(tmp_path / "store")
    d = pd.to_datetime([p[0] for p in points])
    df = pd.DataFrame(
        {
            "date": d,
            "realtime_start": pd.to_datetime([p[1] for p in points]),
            "realtime_end": pd.Timestamp("2262-04-10"),
            "value": [p[2] for p in points],
        }
    )
    store.write("macro/fred/DGS1MO", df)
    return PointInTimeStore(store, load_yaml("data.yaml"))


def test_dgs1mo_point_du_31_janvier_publie_le_1er_fevrier_n_est_pas_servi_avant_t(tmp_path):
    from amundi_agentic.tools.market_data import MarketDataAdapter

    pit = _store_taux(
        tmp_path, [("2024-01-30", "2024-01-31", 5.40), ("2024-01-31", "2024-02-01", 9.99)]
    )
    assert MarketDataAdapter(pit.as_of(T)).risk_free_annual().value == pytest.approx(0.054)
    assert MarketDataAdapter(pit.as_of(date(2024, 2, 2))).risk_free_annual().value == pytest.approx(
        0.0999
    )


def test_taux_suivi_ne_sert_pas_un_point_publie_apres_as_of_performance(tmp_path):
    pit = _store_taux(
        tmp_path,
        [("2024-05-30", "2024-05-31", 5.50), ("2024-05-31", "2024-06-03", 8.00)],
    )
    cfg = charger_config()
    s = SourceReelle.__new__(SourceReelle)
    s._pit = pit
    taux = s.taux_suivi(cfg)
    assert list(taux.index) == [
        pd.Timestamp("2024-05-30")
    ]  # le point du 31 mai publié le 3 juin : non servi
    assert float(taux.iloc[-1]) == 5.5


def test_prix_suivi_refuse_tout_prix_apres_fin_de_suivi(tmp_path):
    store = ParquetStore(tmp_path / "store")
    idx = pd.bdate_range("2024-01-02", "2024-07-31")
    store.write(
        "prices/AAA",
        pd.DataFrame(
            {
                "date": idx,
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 100.0,
                "volume": 1,
                "dividends": 0.0,
                "splits": 0.0,
            }
        ),
    )
    pit = PointInTimeStore(store, load_yaml("data.yaml"))
    cfg = charger_config()
    s = SourceReelle.__new__(SourceReelle)
    s._pit = pit
    df = s.prix_suivi(["AAA"], cfg)
    assert df.index.max() == pd.Timestamp("2024-05-31") and df.index.min() == pd.Timestamp(
        "2024-02-01"
    )
    assert len(df) == len(pd.bdate_range("2024-02-01", "2024-05-31"))


def test_as_of_performance_exactement_au_lendemain_de_fin_de_suivi():
    cfg = charger_config()
    assert cfg.cible.as_of_performance == date(2024, 6, 1) and cfg.cible.fin_suivi == date(
        2024, 5, 31
    )
    with pytest.raises(ConfigReplicationError):
        charger_config(overrides={"cible": {"as_of_performance": "2024-05-31"}})
    with pytest.raises(ConfigReplicationError):
        charger_config(overrides={"cible": {"fin_suivi": "2024-01-15"}})


_ = json
