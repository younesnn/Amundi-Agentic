# ruff: noqa: E501
"""Performance, portefeuilles, inférence de la réplication : valeurs calculées à la main."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from amundi_agentic.data.models import LookAheadError
from amundi_agentic.evaluation import inference as inf
from amundi_agentic.evaluation import perf
from amundi_agentic.evaluation.portefeuilles import decisions
from amundi_agentic.tools.finance import sharpe_ratio

AS_OF = date(2024, 6, 1)
FIN = date(2024, 5, 31)


def _prix(n=40, seed=0, tickers=("A", "B", "C")):
    idx = pd.bdate_range("2024-02-01", periods=n)
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {t: 100 * np.cumprod(1 + rng.normal(0.001, 0.01, n)) for t in tickers}, index=idx
    )


def test_valeur_equiponderee_achat_conservation():
    p = _prix()
    v = perf.valeur_portefeuille(p, ["A", "B"])
    attendu = (p[["A", "B"]] / p[["A", "B"]].iloc[0]).mean(axis=1)
    assert np.allclose(v, attendu) and v.iloc[0] == 1.0


def test_mesure_reutilise_les_formules_du_papier():
    p = _prix(60)
    v = perf.valeur_portefeuille(p, ["A", "B", "C"])
    m = perf.mesurer(v, AS_OF, FIN, 0.05, 21)
    assert math.isclose(m.cumul, v.iloc[-1] / v.iloc[0] - 1)
    assert math.isclose(m.sharpe, sharpe_ratio(v, AS_OF, 59, rf_annual=0.05).value)
    r = perf.rendements(v)
    assert math.isclose(m.volatilite, r.std(ddof=1) * math.sqrt(252))
    assert m.perte_max <= 0 and m.sharpe_glissant


def test_tresorerie_capitalisee_au_taux_sans_risque_sharpe_non_defini():
    p = _prix()
    taux = pd.Series(5.0, index=p.index.union(p.index - pd.Timedelta(days=5)))
    ta = perf.taux_quotidiens(taux, p.index)
    v = perf.valeur_portefeuille(p, [], ta)
    n = len(p) - 1
    assert math.isclose(v.iloc[-1], 1.05 ** (n / 252), rel_tol=1e-9)
    m = perf.mesurer(v, AS_OF, FIN, 0.05, 21)
    assert m.sharpe is None and m.notes


def test_taux_du_jour_n_utilise_pas_la_valeur_du_jour_meme():
    idx = pd.bdate_range("2024-02-01", periods=4)
    taux = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    ta = perf.taux_quotidiens(taux, idx)
    assert list(ta.iloc[1:]) == [0.01, 0.02, 0.03]


def test_performance_refuse_tout_prix_apres_fin_de_suivi():
    p = _prix(120)  # dépasse le 2024-05-31
    assert p.index.max() > pd.Timestamp(FIN)
    with pytest.raises(LookAheadError):
        perf.fenetre_suivi(p, date(2024, 2, 1), FIN)
    with pytest.raises(LookAheadError):
        perf.mesurer(perf.valeur_portefeuille(p, ["A"]), AS_OF, FIN, 0.0, 21)


def test_aucune_donnee_apres_fin_dans_la_mesure_synthetique():
    from amundi_agentic.evaluation.repl_config import charger_config
    from amundi_agentic.evaluation.sources import SourceSynthetique

    cfg = charger_config()
    s = SourceSynthetique(cfg, n_pool=5)
    px = s.prix_suivi(["SYN01", "ZS"], cfg)
    assert px.index.max() <= pd.Timestamp(cfg.cible.fin_suivi)
    assert px.index.min() >= pd.Timestamp(cfg.cible.date_decision)


# --------------------------------------------------------------------------- mapping
def _e(v=None, f=None, final=None):
    votes = {}
    if v is not None:
        votes["valuation"] = v
    if f is not None:
        votes["fundamental"] = f
    return {"votes_tour0": votes, "final": final}


def test_mapping_buy_si_positif_sinon_sell():
    d = decisions(_e(1, 0, {"niveau": 1, "statut": "consensus"}), 0)
    assert d == {
        "valuation_seul": "BUY",
        "fundamental_seul": "SELL",
        "ET": "SELL",
        "OU": "BUY",
        "multi_agent": "BUY",
    }
    assert decisions(_e(-2, 0, {"niveau": 0, "statut": "unanime"}), 0)["multi_agent"] == "SELL"


def test_abstention_et_voix_unique_excluent_jamais_sell_implicite():
    d = decisions(_e(2, None, {"niveau": 1, "statut": "voix_unique"}), 0)
    assert d["fundamental_seul"] is None and d["ET"] is None and d["OU"] is None
    assert d["multi_agent"] is None and d["valuation_seul"] == "BUY"
    assert decisions(_e(), 0) == dict.fromkeys(decisions(_e(), 0)) and all(
        x is None for x in decisions(_e(), 0).values()
    )
    s = decisions(_e(2, None, None), 0, abstention_sell=True)
    assert s["fundamental_seul"] == "SELL" and s["multi_agent"] == "SELL" and s["ET"] == "SELL"


# --------------------------------------------------------------------------- inférence
def test_wilson_valeurs_connues():
    lo, hi = inf.wilson(8, 10, 0.95)
    assert math.isclose(lo, 0.4902, abs_tol=1e-3) and math.isclose(hi, 0.9433, abs_tol=1e-3)
    assert inf.wilson(0, 0) is None
    lo, hi = inf.wilson(0, 10)
    assert lo == 0 and 0.2 < hi < 0.35


def test_kappa():
    assert inf.kappa_cohen(list("ABAB"), list("ABAB")) == 1.0
    assert math.isclose(inf.kappa_cohen(list("AABB"), list("ABAB")), 0.0)
    assert inf.kappa_cohen(["A"] * 3, ["A"] * 3) is None
    assert inf.kappa_cohen([], []) is None


def test_distribution_exacte_enumere_toutes_les_combinaisons():
    rel = np.array([1.0, 1.1, 0.9, 1.2, 0.8])
    d = inf.distribution_aleatoire(rel, 2, observe=0.15, max_exact=100, n_echantillon=10, graine=1)
    assert d.exacte and d.n_combinaisons == 10 and d.n_evalues == 10
    vals = sorted((rel[i] + rel[j]) / 2 - 1 for i in range(5) for j in range(i + 1, 5))
    assert math.isclose(d.mediane, float(np.median(vals)))
    assert math.isclose(d.p_superieur_ou_egal, sum(v >= 0.15 - 1e-12 for v in vals) / 10)
    ech = inf.distribution_aleatoire(rel, 2, observe=None, max_exact=5, n_echantillon=50, graine=1)
    assert not ech.exacte and ech.n_evalues == 50


def test_bootstrap_stationnaire_reproductible_et_longueur_de_bloc():
    rng = np.random.default_rng(0)
    idx = inf.indices_bootstrap_stationnaire(50, 2000, 5.0, rng)
    assert idx.shape == (2000, 50) and idx.min() >= 0 and idx.max() < 50
    suite = (np.diff(idx, axis=1) % 50) == 1
    assert 0.7 < suite.mean() < 0.9  # P(continuer) = 1 - 1/5
    ra = np.random.default_rng(1).normal(0.001, 0.01, 60)
    rb = np.random.default_rng(2).normal(0.0, 0.01, 60)
    kw = {"longueur_moyenne": 5, "n_rep": 500, "graine": 3, "niveau": 0.95}
    a = inf.bootstrap_difference_cumulee(ra, rb, **kw)
    assert a == inf.bootstrap_difference_cumulee(ra, rb, **kw)
    assert a.bas <= a.estimation <= a.haut or a.contient_zero in (True, False)
    zero = inf.bootstrap_difference_cumulee(ra, ra, **kw)
    assert zero.estimation == 0 and zero.bas == zero.haut == 0 and zero.contient_zero


def test_sharpe_vectorise_egal_a_tools_finance():
    p = _prix(50)["A"]
    r = p.pct_change().dropna().to_numpy()
    attendu = sharpe_ratio(p, AS_OF, 49, rf_annual=0.04).value
    assert math.isclose(inf.sharpe_depuis_rendements(r, 0.04), attendu)
    ic = inf.bootstrap_sharpe(r, 0.04, longueur_moyenne=5, n_rep=300, graine=1, niveau=0.95)
    assert ic is not None and ic[0] < ic[1]
    assert (
        inf.bootstrap_sharpe(
            np.zeros(30) + 1e-9, 0.0, longueur_moyenne=5, n_rep=100, graine=1, niveau=0.95
        )
        is None
    )
