# ruff: noqa: E501
"""Revue indépendante : calculs de la réplication recalculés avec des oracles écrits ici (numpy,
itertools, arithmétique), sans réutiliser les fonctions testées pour fabriquer l'attendu."""

from __future__ import annotations

import math
from datetime import date
from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.evaluation import analyse, perf
from amundi_agentic.evaluation import inference as inf
from amundi_agentic.evaluation.portefeuilles import PORTEFEUILLES, decisions
from amundi_agentic.evaluation.repl_config import charger_config
from amundi_agentic.evaluation.sources import SourceReelle
from amundi_agentic.evaluation.tirage import Tirage

T, FIN, AS_OF = date(2024, 2, 1), date(2024, 5, 31), date(2024, 6, 1)
IDX = pd.bdate_range("2024-02-01", "2024-05-31")
SQ = math.sqrt(252)


def _prix(n_titres=4, graine=3):
    rng = np.random.default_rng(graine)
    r = rng.normal(0.0005, 0.012, (len(IDX), n_titres))
    r[0] = 0.0
    return pd.DataFrame(
        100 * np.cumprod(1 + r, axis=0), index=IDX, columns=[f"T{i}" for i in range(n_titres)]
    )


# ======================================================================= valeur du portefeuille
def test_equiponde_a_l_entree_achat_et_conservation_pas_de_reequilibrage_quotidien():
    p = _prix()
    titres = ["T0", "T1", "T2"]
    v = perf.valeur_portefeuille(p, titres)
    oracle = (p[titres] / p[titres].iloc[0]).mean(axis=1)  # poids initiaux 1/3 qui DÉRIVENT
    np.testing.assert_allclose(v.to_numpy(), oracle.to_numpy(), rtol=1e-13)
    rend = p[titres].pct_change().iloc[1:]
    quotidien_reeq = (1 + rend.mean(axis=1)).cumprod()  # ce que ferait un rééquilibrage chaque jour
    assert not np.allclose(v.iloc[1:].to_numpy(), quotidien_reeq.to_numpy(), rtol=1e-6)
    assert v.iloc[0] == 1.0


def test_entree_a_la_premiere_cloture_a_partir_de_t_et_refus_apres_fin():
    p = _prix()
    avant = pd.DataFrame({"T0": [90.0, 91.0]}, index=pd.to_datetime(["2024-01-30", "2024-01-31"]))
    fen = perf.fenetre_suivi(pd.concat([avant, p[["T0"]]]), T, FIN)
    assert fen.index[0] == pd.Timestamp("2024-02-01") and fen.index[-1] == pd.Timestamp(
        "2024-05-31"
    )
    # t un samedi : l'entrée est la séance du lundi
    sam = perf.fenetre_suivi(p[["T0"]], date(2024, 3, 2), FIN)
    assert sam.index[0] == pd.Timestamp("2024-03-04")
    from amundi_agentic.data.models import LookAheadError

    hostile = pd.concat(
        [p[["T0"]], pd.DataFrame({"T0": [1e9]}, index=pd.to_datetime(["2024-06-03"]))]
    )
    with pytest.raises(LookAheadError):
        perf.fenetre_suivi(hostile, T, FIN)


def test_cumul_vol_sharpe_perte_max_oracle():
    p = _prix()
    titres = ["T0", "T2"]
    v = perf.valeur_portefeuille(p, titres)
    rf = 0.0525
    m = perf.mesurer(v, AS_OF, FIN, rf, 21)
    val = v.to_numpy()
    r = val[1:] / val[:-1] - 1
    n = len(r)
    cum = val[-1] / val[0] - 1
    ann = (1 + cum) ** (252 / n) - 1
    vol = r.std(ddof=1) * SQ
    assert m.cumul == pytest.approx(cum, rel=1e-12)
    assert m.annualise == pytest.approx(ann, rel=1e-12)
    assert m.volatilite == pytest.approx(vol, rel=1e-12)
    assert m.sharpe == pytest.approx((ann - rf) / vol, rel=1e-11)
    pic = np.maximum.accumulate(val)
    dd = val / pic - 1
    k = int(np.argmin(dd))
    j = int(np.argmax(val[: k + 1]))
    assert m.perte_max == pytest.approx(dd[k], rel=1e-12)
    assert m.pic == str(v.index[j].date()) and m.creux == str(v.index[k].date())
    assert m.n_rendements == n == len(IDX) - 1 == 85 or m.n_rendements == len(IDX) - 1


def test_sharpe_glissant_fenetre_de_la_config_oracle_pandas():
    cfg = charger_config()
    w = cfg.performance.fenetre_sharpe_glissant
    assert w == 21
    p = _prix()
    v = perf.valeur_portefeuille(p, ["T1", "T3"])
    rf = 0.05
    m = perf.mesurer(v, AS_OF, FIN, rf, w)
    r = v.pct_change()
    rfd = (1 + rf) ** (1 / 252) - 1
    att = ((r.rolling(w).mean() - rfd) / r.rolling(w).std(ddof=1)).iloc[w:]
    got = pd.Series({pd.Timestamp(k): x for k, x in m.sharpe_glissant.items()})
    np.testing.assert_allclose(got.to_numpy(), att.to_numpy(), rtol=1e-9)


def test_taux_moyen_dgs1mo_en_decimal_sur_la_fenetre_et_jamais_hors_fenetre():
    idx = pd.bdate_range("2024-01-02", "2024-05-31")
    s = pd.Series(5.0, index=idx)
    s[s.index >= "2024-02-01"] = 5.5
    s[s.index > "2024-05-31"] = 9.0
    assert perf.taux_moyen(s, T, FIN) == pytest.approx(0.055)
    mixte = pd.Series(
        [5.0, 6.0, 7.0, 99.0],
        index=pd.to_datetime(["2024-02-01", "2024-02-02", "2024-02-05", "2024-06-03"]),
    )
    assert perf.taux_moyen(mixte, T, FIN) == pytest.approx(
        0.06
    )  # le point du 3 juin est hors fenêtre


def test_portefeuille_vide_tresorerie_capitalisee_au_taux_de_la_veille():
    p = _prix()
    taux_pct = pd.Series(5.3, index=pd.bdate_range("2024-01-02", "2024-05-31"))
    taux_pct[taux_pct.index >= "2024-04-01"] = 5.0
    ta = perf.taux_quotidiens(taux_pct, p.index)
    v = perf.valeur_portefeuille(p, [], ta)
    # oracle : valeur_d = valeur_{d-1} x (1 + r_{d-1})^(1/252), r en vigueur la VEILLE (jamais le jour même)
    att = [1.0]
    for i in range(1, len(p)):
        r_veille = 5.3 / 100 if p.index[i - 1] < pd.Timestamp("2024-04-01") else 5.0 / 100
        att.append(att[-1] * (1 + r_veille) ** (1 / 252))
    np.testing.assert_allclose(v.to_numpy(), np.array(att), rtol=1e-12)
    # le jour du changement de taux (2024-04-01) utilise encore l'ancien taux
    i = list(p.index).index(pd.Timestamp("2024-04-01"))
    assert v.iloc[i] / v.iloc[i - 1] == pytest.approx((1.053) ** (1 / 252))


def test_adj_close_dividende_rendement_total_oracle(tmp_path):
    store = ParquetStore(tmp_path / "store")
    idx = pd.bdate_range("2024-01-02", "2024-07-31")
    div = pd.Series(0.0, index=idx)
    div[pd.Timestamp("2024-03-15")] = 2.0
    store.write(
        "prices/AAA",
        pd.DataFrame(
            {
                "date": idx,
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
                "volume": 1,
                "dividends": div.to_numpy(),
                "splits": 0.0,
            }
        ),
    )
    pit = PointInTimeStore(store, load_yaml("data.yaml"))
    s = SourceReelle.__new__(SourceReelle)
    s._pit = pit
    df = s.prix_suivi(["AAA"], charger_config())
    # cours brut constant à 100, dividende de 2 le 15 mars : le rendement total est de +2,04 % (2 / 98)
    # selon le facteur 1 - D/P_veille appliqué aux barres antérieures : 100 x (1 - 2/100) = 98 avant, 100 après
    assert df["AAA"].iloc[0] == pytest.approx(98.0, rel=1e-9)
    assert df["AAA"].iloc[-1] == pytest.approx(100.0, rel=1e-9)
    assert df["AAA"].iloc[-1] / df["AAA"].iloc[0] - 1 == pytest.approx(2.0 / 98.0, rel=1e-9)
    assert df.index.max() == pd.Timestamp("2024-05-31")


# ======================================================================= distribution exacte
@pytest.mark.parametrize("n,m", [(15, 1), (15, 2), (15, 7), (10, 10), (6, 3)])
def test_distribution_exacte_denombrement_et_rangs_par_force_brute(n, m):
    rng = np.random.default_rng(n * 100 + m)
    rel = 1 + rng.normal(0.02, 0.1, n)
    obs = float(rel[:m].mean() - 1)
    d = inf.distribution_aleatoire(rel, m, observe=obs, max_exact=10**6, n_echantillon=10, graine=0)
    tous = np.array([rel[list(c)].mean() - 1 for c in combinations(range(n), m)])
    assert d.exacte and d.n_combinaisons == math.comb(n, m) == len(tous) == d.n_evalues
    assert d.mediane == pytest.approx(np.quantile(tous, 0.5)) and d.moyenne == pytest.approx(
        tous.mean()
    )
    assert d.p_superieur_ou_egal == pytest.approx(np.mean(tous >= obs - 1e-12))
    assert d.percentile_observe == pytest.approx(np.mean(tous < obs - 1e-12))
    # le portefeuille observé fait partie de la distribution : au moins 1 / C portefeuilles >= lui
    assert d.p_superieur_ou_egal >= 1 / math.comb(n, m) - 1e-12


def test_distribution_cas_limites_m_zero_m_un_m_egal_n_echantillon():
    rel = np.array([1.1, 0.9, 1.0, 1.2])
    with pytest.raises(ValueError):
        inf.distribution_aleatoire(rel, 0, observe=None, max_exact=100, n_echantillon=10, graine=0)
    with pytest.raises(ValueError):
        inf.distribution_aleatoire(rel, 5, observe=None, max_exact=100, n_echantillon=10, graine=0)
    d1 = inf.distribution_aleatoire(rel, 1, observe=0.2, max_exact=100, n_echantillon=10, graine=0)
    assert d1.n_combinaisons == 4 and d1.p_superieur_ou_egal == pytest.approx(
        0.25
    )  # seul le 1,2 atteint +20 %
    dn = inf.distribution_aleatoire(
        rel, 4, observe=float(rel.mean() - 1), max_exact=100, n_echantillon=10, graine=0
    )
    assert dn.n_combinaisons == 1 and dn.p_superieur_ou_egal == 1.0 and dn.percentile_observe == 0.0
    # C(40, 20) > max_exact : échantillon reproductible, signalé « non exact »
    rel40 = np.linspace(0.8, 1.3, 40)
    a = inf.distribution_aleatoire(
        rel40, 20, observe=0.0, max_exact=1000, n_echantillon=500, graine=7, cle="x"
    )
    b = inf.distribution_aleatoire(
        rel40, 20, observe=0.0, max_exact=1000, n_echantillon=500, graine=7, cle="x"
    )
    assert not a.exacte and a == b and a.n_evalues == 500


# ======================================================================= Wilson, kappa, bootstrap
@pytest.mark.parametrize(
    "k,n,bas,haut",
    [
        (5, 10, 0.2366, 0.7634),
        (0, 10, 0.0, 0.2775),
        (10, 10, 0.7225, 1.0),
        (50, 100, 0.4038, 0.5962),
    ],
)
def test_wilson_valeurs_de_reference(k, n, bas, haut):
    b, h = inf.wilson(k, n, 0.95)
    assert b == pytest.approx(bas, abs=6e-4) and h == pytest.approx(haut, abs=6e-4)
    assert inf.wilson(0, 0) is None


def test_kappa_valeurs_connues():
    assert inf.kappa_cohen([1, 1, 0, 0], [1, 0, 0, 0]) == pytest.approx(0.5)
    assert inf.kappa_cohen(list("ABAB"), list("ABAB")) == pytest.approx(1.0)
    assert (
        inf.kappa_cohen(list("AAAA"), list("BBBB")) is None
        or inf.kappa_cohen(list("AAAA"), list("BBBB")) <= 0
    )
    assert inf.kappa_cohen(list("ABAB"), list("BABA")) == pytest.approx(-1.0)
    assert inf.kappa_cohen([], []) is None
    # trois catégories dont EXCLU (cas du rapport)
    a = ["BUY", "SELL", "EXCLU", "BUY", "SELL", "EXCLU"]
    b = ["BUY", "SELL", "BUY", "BUY", "EXCLU", "EXCLU"]
    po = 4 / 6
    pe = (2 / 6) * (3 / 6) + (2 / 6) * (1 / 6) + (2 / 6) * (2 / 6)
    assert inf.kappa_cohen(a, b) == pytest.approx((po - pe) / (1 - pe))


def test_bootstrap_stationnaire_longueur_de_bloc_geometrique_et_reproductibilite():
    bloc = 5.0
    idx = inf.indices_bootstrap_stationnaire(200, 4000, bloc, np.random.default_rng(1))
    continuation = (idx[:, 1:] == (idx[:, :-1] + 1) % 200).mean()
    # P(continuer) = 1 - 1/L, plus 1/(n L) de retomber par hasard sur l'indice suivant
    assert continuation == pytest.approx(1 - 1 / bloc + 1 / (200 * bloc), abs=0.01)
    longueur_moyenne = 1 / (1 - continuation)
    assert longueur_moyenne == pytest.approx(bloc, rel=0.05)
    a = inf.indices_bootstrap_stationnaire(50, 100, 5.0, np.random.default_rng(9))
    b = inf.indices_bootstrap_stationnaire(50, 100, 5.0, np.random.default_rng(9))
    assert (a == b).all() and a.min() >= 0 and a.max() < 50


def test_bootstrap_difference_coherent_avec_un_bootstrap_par_blocs_mobiles_de_reference():
    rng = np.random.default_rng(5)
    n = 85
    ra = rng.normal(0.0008, 0.01, n)
    rb = rng.normal(0.0002, 0.01, n)
    iv = inf.bootstrap_difference_cumulee(
        ra, rb, longueur_moyenne=5, n_rep=4000, graine=11, niveau=0.95
    )
    # référence : bootstrap par blocs mobiles de 5 jours appariés, écrit ici
    ref = np.random.default_rng(12)
    bloc = 5
    diffs = []
    for _ in range(4000):
        idx = []
        while len(idx) < n:
            d = int(ref.integers(0, n - bloc + 1))
            idx += list(range(d, d + bloc))
        idx = np.array(idx[:n])
        diffs.append(np.prod(1 + ra[idx]) - np.prod(1 + rb[idx]))
    bas, haut = np.quantile(diffs, [0.025, 0.975])
    assert iv.estimation == pytest.approx(np.prod(1 + ra) - np.prod(1 + rb), rel=1e-12)
    assert (iv.haut - iv.bas) == pytest.approx(haut - bas, rel=0.15)
    assert iv.bas == pytest.approx(bas, abs=0.02) and iv.haut == pytest.approx(haut, abs=0.02)
    # reproductible, et sans graine identique les bornes diffèrent légèrement
    iv2 = inf.bootstrap_difference_cumulee(
        ra, rb, longueur_moyenne=5, n_rep=4000, graine=11, niveau=0.95
    )
    iv3 = inf.bootstrap_difference_cumulee(
        ra, rb, longueur_moyenne=5, n_rep=4000, graine=12, niveau=0.95
    )
    assert iv == iv2 and iv != iv3


def test_bootstrap_taux_d_exclusion_de_zero_entre_deux_portefeuilles_aleatoires_mesure():
    """Mesure (dispersion du choix des titres ignorée par un bootstrap de jours) : fréquence à
    laquelle l'IC à 95 % de la différence entre deux sous-ensembles ALÉATOIRES de 7 titres exclut 0.
    Mesuré : environ 7 % sur ces données (nominal 5 %) : légèrement permissif, pas dramatique."""
    rng = np.random.default_rng(0)
    n_j, n_t, essais, exclu = 85, 15, 150, 0
    for _ in range(essais):
        r = rng.normal(0.0004, 0.015, (n_j, n_t))
        a, b = rng.permutation(n_t)[:7], rng.permutation(n_t)[:7]
        pa = np.cumprod(1 + r[:, a], axis=0).mean(axis=1)
        pb = np.cumprod(1 + r[:, b], axis=0).mean(axis=1)
        ra, rb = pa[1:] / pa[:-1] - 1, pb[1:] / pb[:-1] - 1
        iv = inf.bootstrap_difference_cumulee(
            ra, rb, longueur_moyenne=5, n_rep=300, graine=3, niveau=0.95
        )
        exclu += not iv.contient_zero
    assert exclu / essais < 0.20


# ======================================================================= mapping et portefeuilles
def _enreg(v, f, final=None, statut="consensus"):
    votes = {}
    if v is not None:
        votes["valuation"] = v
    if f is not None:
        votes["fundamental"] = f
    return {
        "votes_tour0": votes,
        "final": None if final is None else {"niveau": final, "statut": statut},
    }


@pytest.mark.parametrize(
    "v,f,final,attendu",
    [
        (1, 1, 1, ("BUY", "BUY", "BUY", "BUY", "BUY")),
        (2, -1, 0, ("BUY", "SELL", "SELL", "BUY", "SELL")),
        (0, 0, -2, ("SELL", "SELL", "SELL", "SELL", "SELL")),
        (-1, 1, 1, ("SELL", "BUY", "SELL", "BUY", "BUY")),
    ],
)
def test_mapping_niveau_superieur_a_zero_buy_zero_et_negatif_sell(v, f, final, attendu):
    d = decisions(_enreg(v, f, final), 0)
    assert tuple(d[p] for p in PORTEFEUILLES) == attendu  # valuation, fundamental, ET, OU, multi


def test_abstention_rejet_et_voix_unique_excluent_jamais_sell_et_variante_sell():
    d = decisions(_enreg(1, None, 1, "voix_unique"), 0)
    assert d == {
        "valuation_seul": "BUY",
        "fundamental_seul": None,
        "ET": None,
        "OU": None,
        "multi_agent": None,
    }
    d_sell = decisions(_enreg(1, None, 1, "voix_unique"), 0, abstention_sell=True)
    assert (
        d_sell["fundamental_seul"]
        == d_sell["ET"]
        == d_sell["OU"]
        == d_sell["multi_agent"]
        == "SELL"
    )
    sans_vue = decisions({"votes_tour0": {}, "final": None}, 0)
    assert all(x is None for x in sans_vue.values())
    # ET et OU exigent les DEUX votes : un vote manquant exclut des deux (cohérent avec le rapport)
    assert decisions(_enreg(2, None, None), 0)["OU"] is None


def test_mapping_seuil_de_la_config_et_pas_de_ge_zero():
    assert charger_config().mapping.buy_si_niveau_superieur_a == 0
    assert decisions(_enreg(0, 0, 0), 0)["valuation_seul"] == "SELL"  # 0 n'est pas BUY (pas de >=)


# ---- portefeuilles construits depuis le BON niveau, via `analyser`
TIT = ["ZS"] + [f"T{i:02d}" for i in range(14)]


class _Src:
    synthetique = True

    def __init__(self):
        rng = np.random.default_rng(2)
        r = rng.normal(0.0004, 0.014, (len(IDX), len(TIT)))
        r[0] = 0
        self.p = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=IDX, columns=TIT)
        self.tx = pd.Series(5.3, index=pd.bdate_range("2024-01-02", "2024-05-31"))

    def prix_suivi(self, titres, cfg):
        return self.p[list(titres)]

    def taux_suivi(self, cfg):
        return self.tx


def _debat(v, f, final, statut="consensus"):
    votes = {k: x for k, x in (("valuation", v), ("fundamental", f)) if x is not None}
    return {
        "statut_debat": "ok",
        "votes_tour0": votes,
        "final": None
        if final is None
        else {
            "niveau": final,
            "statut": statut,
            "confiance": 0.5,
            "tours": 1,
            "plafonnee_par": None,
        },
        "sans_decision": None,
        "votants": ["valuation", "fundamental"],
        "rejets": [],
        "prompts_sha256": {},
        "modeles_servis": [],
        "appels_reels": 0,
        "cache_hits": 0,
        "par_fournisseur": {},
        "tokens_entree": 0,
        "tokens_sortie": 0,
        "duree_s": 0.0,
    }


def _analyse(plan):
    cfg = charger_config(
        overrides={
            "tirage": {"n_titres": 14, "n_tirages_secondaires": 0},
            "inference": {"bootstrap": {"n_reechantillonnages": 100}},
            "profils": ["risk_averse"],
            "executions": [
                {"nom": "baseline", "temperature": 0.0, "paraphrase": None, "graine_llm": 0}
            ],
        }
    )
    debats = {
        f"baseline|risk_averse|{t}": _debat(
            *plan[t], *(("voix_unique",) if None in plan[t][:2] else ())
        )
        for t in TIT
    }
    tir = Tirage(tuple(TIT[1:]), tuple(TIT), tuple(TIT[1:]))
    return analyse.analyser(cfg, _Src(), debats, {}, tir, TIT, ["baseline"])


def test_chaque_portefeuille_est_construit_depuis_le_bon_niveau_et_abstention_exclue():
    plan = {t: (-1, -1, -1) for t in TIT}
    plan["T00"] = (1, -1, -1)  # Valuation seul BUY ; OU BUY
    plan["T01"] = (-1, 2, -1)  # Fundamental seul BUY ; OU BUY
    plan["T02"] = (1, 1, -1)  # ET, OU, V, F BUY ; multi SELL
    plan["T03"] = (-1, -1, 2)  # multi BUY seul
    plan["T04"] = (1, None, 1)  # Fundamental absent : V BUY ; ET/OU/multi exclus
    plan["T05"] = (1, 1, 1)  # tous BUY
    plan["T06"] = (1, 1, 1)  # multi voix_unique : exclu du multi
    plan["T06"] = (1, 1, 1)
    deb = {t: _debat(*plan[t]) for t in TIT}
    deb["T04"] = _debat(1, None, 1, "voix_unique")  # un seul votant : statut voix_unique
    deb["T06"] = _debat(1, 1, 1, "voix_unique")
    cfg = charger_config(
        overrides={
            "tirage": {"n_titres": 14, "n_tirages_secondaires": 0},
            "inference": {"bootstrap": {"n_reechantillonnages": 100}},
            "profils": ["risk_averse"],
            "executions": [
                {"nom": "baseline", "temperature": 0.0, "paraphrase": None, "graine_llm": 0}
            ],
        }
    )
    debats = {f"baseline|risk_averse|{t}": d for t, d in deb.items()}
    tir = Tirage(tuple(TIT[1:]), tuple(TIT), tuple(TIT[1:]))
    res = analyse.analyser(cfg, _Src(), debats, {}, tir, TIT, ["baseline"])
    pf = res["executions"]["baseline"]["risk_averse"]["portefeuilles"]
    assert sorted(pf["valuation_seul"]["titres"]) == ["T00", "T02", "T04", "T05", "T06"]
    assert sorted(pf["fundamental_seul"]["titres"]) == ["T01", "T02", "T05", "T06"]
    assert sorted(pf["ET"]["titres"]) == ["T02", "T05", "T06"]
    assert sorted(pf["OU"]["titres"]) == ["T00", "T01", "T02", "T05", "T06"]
    assert sorted(pf["multi_agent"]["titres"]) == ["T03", "T05"]
    dec = res["executions"]["baseline"]["risk_averse"]["decompte"]["multi_agent"]["primaire"]
    assert dec["exclus"] == 2 and dec["BUY"] == 2  # T04 (vote manquant) et T06 (voix unique)
    assert (
        dec["BUY"] + dec["SELL"] + dec["exclus"] == 15
    )  # ZS inclus dans `primaire` = 15 titres : voir ci-dessous


def test_sensibilite_abstention_sell_ne_change_aucun_portefeuille_limite_documentee():
    """LIMITE (non bloquante) : un portefeuille ne contient que des BUY ; lire une abstention comme
    SELL ne peut donc rien changer à ses titres, ni à sa performance. La « sensibilité » du rapport
    est vide d'information : elle ne s'écarte jamais du résultat principal."""
    plan = {t: (1, 1, 1) for t in TIT}
    plan["T00"] = (1, None, 1)
    plan["T01"] = (None, None, None)
    res = _analyse(plan)
    for nom, d in res["executions"]["baseline"]["risk_averse"]["portefeuilles"].items():
        s = d["sensibilite_abstention_sell"]
        assert s["titres"] == d["titres"], nom
        assert s["cumul"] == d["cumul"], nom


def test_portefeuille_vide_en_tresorerie_compare_a_un_portefeuille_d_actions_artefact_signale():
    """Si le multi-agent est vide (toutes décisions exclues ou SELL), son rendement est celui de la
    trésorerie : la comparaison avec un portefeuille d'actions mélange deux natures d'actif."""
    plan = {
        t: (
            1,
            None,
            1,
        )
        for t in TIT
    }  # Fundamental absent partout : ET, OU, multi, Fundamental vides
    res = _analyse(plan)
    pf = res["executions"]["baseline"]["risk_averse"]["portefeuilles"]
    for nom in ("fundamental_seul", "ET", "OU", "multi_agent"):
        assert pf[nom]["tresorerie"] is True and pf[nom]["m"] == 0
    assert pf["valuation_seul"]["tresorerie"] is False
    assert pf["multi_agent"]["cumul"] == pytest.approx(res["fenetre"]["cumul_tresorerie"])
