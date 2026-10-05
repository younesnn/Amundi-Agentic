"""Contre-vérification indépendante des corrections N1 à N7 des outils de calcul (phase 3).

Chaque attendu est calculé dans le test (oracle numpy/pandas ou arithmétique écrite à la main), pas
lu dans la sortie de l'outil. Aucun réseau, aucun LLM, aucune clé.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import textwrap
import time
from datetime import UTC, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from tools_helpers import apres, avec_futur, depuis_rendements, marche_aleatoire, serie

from amundi_agentic.tools import base, finance, momentum, risk
from amundi_agentic.tools.base import DegenerateSeriesError, ToolError
from amundi_agentic.tools.macro_regime import macro_regime

SQ252 = math.sqrt(252)
_ENV_HERITE = {k: os.environ[k] for k in ("PYTHONPATH",) if k in os.environ}


def _alternee(vol_annuelle: float, n: int = 300) -> pd.Series:
    """Rendements +a, -a alternés dont l'écart-type d'échantillon (ddof=1) annualisé vaut
    exactement `vol_annuelle` sur les 252 derniers rendements (252 pair : moyenne nulle)."""
    sigma = vol_annuelle / SQ252
    a = sigma * math.sqrt(251 / 252)  # std ddof=1 de ±a (252 valeurs) = a x racine(252/251)
    r = np.array([a if k % 2 == 0 else -a for k in range(n)])
    return depuis_rendements(r)


# ======================================================================== N1 : tolérance de seuil
@pytest.mark.parametrize("ecart", [-1e-6, -1e-9 * 1.5, -1e-9 / 2, 0.0, 1e-9, 1e-6])
def test_n1_creux_10_et_20_pourcent_oracle(ecart):
    for seuil in (0.10, 0.20):
        creux = -(seuil + ecart)
        # oracle : atteint ssi |creux| + 1e-9 >= seuil
        atteint = abs(creux) + 1e-9 >= seuil
        niv = risk._niveau(-creux, 0.10, 0.20)
        if seuil == 0.10:
            assert (niv in ("moderee", "elevee")) == atteint
        else:
            assert (niv == "elevee") == atteint


@pytest.mark.parametrize(
    "v,attendu",
    [
        (24.999999999, "moderee"),
        (24.9999, "aucune"),
        (25.0, "moderee"),
        (34.999999999, "elevee"),
        (34.99, "moderee"),
        (35.0, "elevee"),
    ],
)
def test_n1_vix_25_et_35(v, attendu):
    assert risk._niveau(v, 25.0, 35.0) == attendu


@pytest.mark.parametrize(
    "rang,attendu",
    [
        (0.80, "moderee"),
        (0.80 - 1e-6, "aucune"),
        (0.95, "elevee"),
        (0.95 - 1e-6, "moderee"),
        (0.0, "aucune"),
        (1.0, "elevee"),
    ],
)
def test_n1_rang_de_volatilite_080_et_095(rang, attendu):
    assert risk._niveau(rang, 0.80, 0.95) == attendu


def test_n1_de_bout_en_bout_creux_de_10_pourcent_isole_dans_risk_report():
    """Creux courant de 90/100-1 avec rang de volatilité bas : l'alerte modérée vient du creux."""
    rng = np.random.default_rng(2)
    hist = 95.0 * (1 + rng.normal(0, 0.01, 700))  # historique à volatilité élevée
    glisse = 100.0 - 10.0 * np.arange(253) / 252  # 100 -> 90, volatilité quasi nulle
    s = serie(np.concatenate([hist, glisse]))
    p = pd.DataFrame({"A": s})
    t = apres(p)
    rep = risk.risk_report(p, s, t).value
    assert rep.indicateurs["creux_courant:A"] == pytest.approx(-0.10, abs=1e-12)
    assert rep.indicateurs["vol_rang:A"] < 0.80
    assert rep.alertes["A"] == "moderee"


# ======================================================================== N2 : régime, état
def _serie_regime(seed=32, n=1100):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.006, n)
    r[-70:-40] = rng.normal(0, 0.02, 30)
    r[-40:] = rng.normal(0, 0.0095, 40)
    return depuis_rendements(r)


def test_n2_meme_t_meme_previous_meme_resultat_toujours():
    s = _serie_regime()
    t = apres(s)
    for prev in (None, "normal", "haut"):
        rw = 0 if prev is None else None
        a = risk.volatility_regime(s, t, previous=prev, replay_weeks=rw)
        b = risk.volatility_regime(s.copy(), t, previous=prev, replay_weeks=rw)
        assert a.value == b.value and a.meta == b.meta and a.meta.source_id == b.meta.source_id


def test_n2_etat_fourni_ne_depend_ni_de_la_profondeur_ni_du_passe_lointain():
    s = _serie_regime(n=2000)
    t = apres(s)
    ref = risk.volatility_regime(s, t, previous="haut").value
    assert ref.origine == "etat_fourni" and ref.replay_weeks_requested == 0
    assert ref.replay_steps_computed == 0 and ref.changed in (True, False)
    # replay_weeks=0 explicite avec previous : identique
    assert risk.volatility_regime(s, t, previous="haut", replay_weeks=0).value == ref
    # le passé au-delà de la distribution de référence (156 semaines) ne compte pas
    s2 = s.copy()
    s2.iloc[:600] *= np.linspace(1, 5, 600)
    assert risk.volatility_regime(s2, t, previous="haut").value == ref
    # previous + rejeu > 0 refusé
    with pytest.raises(ValueError):
        risk.volatility_regime(s, t, previous="haut", replay_weeks=4)


def test_n2_la_sortie_depend_du_rejeu_seulement_sans_etat_et_l_origine_le_dit():
    s = _serie_regime()
    t = apres(s)
    zero = risk.volatility_regime(s, t, replay_weeks=0).value
    rejeu = risk.volatility_regime(s, t, replay_weeks=8).value
    defaut = risk.volatility_regime(s, t).value
    assert zero.regime == "normal" and zero.origine == "sans_etat"
    assert rejeu.regime == "haut" and rejeu.origine == "rejeu" and rejeu.replay_weeks_requested == 8
    assert defaut.origine == "rejeu" and defaut.replay_weeks_requested == 52
    assert defaut.replay_steps_computed == 52  # 1100 séances : historique suffisant pour 52 pas
    # volatilité et centiles : jamais dépendants de l'état
    assert zero.volatility == rejeu.volatility == defaut.volatility
    assert (zero.p_low, zero.p_high) == (rejeu.p_low, rejeu.p_high)
    # la méta journalise la provenance
    m = risk.volatility_regime(s, t, replay_weeks=8).meta.params
    assert m["origine"] == "rejeu" and m["replay_weeks"] == 8 and m["replay_steps"] == 8
    # etat_fourni : un état « haut » et un état « normal » peuvent donner des résultats différents
    # en zone intermédiaire ; la valeur est alors fixée par l'état fourni, pas par un rejeu caché
    h = risk.volatility_regime(s, t, previous="haut").value
    n = risk.volatility_regime(s, t, previous="normal").value
    assert h.regime == "haut" and n.regime == "normal"
    assert h.volatility == n.volatility


def test_n2_rejeu_incomplet_signale_le_nombre_de_pas_reellement_calcules():
    s = _serie_regime(n=700)  # 700 séances : distribution (156 sem.) + 21 j laisse peu de pas
    res = risk.volatility_regime(s, apres(s), replay_weeks=52, min_weeks=104).value
    assert res.replay_weeks_requested == 52
    assert 0 < res.replay_steps_computed < 52  # l'historique ne permet pas les 52 pas
    assert res.origine == ("rejeu" if res.replay_steps_computed > 0 else "sans_etat")


@pytest.mark.parametrize("m", [4, 8, 20, 52])
def test_n2_chaine_hebdomadaire_avec_previous_egale_le_rejeu_complet(m):
    s = _serie_regime()
    n = len(s)
    prev = None
    for k in range(m, -1, -1):  # t_k = m semaines avant t, ..., t
        sub = s.iloc[: n - 5 * k]
        prev = risk.volatility_regime(
            sub, apres(sub), previous=prev, replay_weeks=0 if prev is None else None
        ).value.regime
    rejeu = risk.volatility_regime(s, apres(s), replay_weeks=m).value
    assert prev == rejeu.regime


def test_n2_chaine_quotidienne_signalee_si_elle_differe_du_rejeu_hebdomadaire():
    """Porter `previous` JOUR après JOUR n'est pas identique par construction au rejeu hebdomadaire
    (l'hystérésis est évaluée plus souvent). On vérifie le résultat sur cette série et on le
    documente : si un jour la chaîne quotidienne diverge, ce test le signale précisément."""
    s = _serie_regime()
    n = len(s)
    prev = None
    for k in range(60, -1, -1):
        sub = s.iloc[: n - k]
        prev = risk.volatility_regime(
            sub, apres(sub), previous=prev, replay_weeks=0 if prev is None else None
        ).value.regime
    assert prev == risk.volatility_regime(s, apres(s)).value.regime == "haut"


def test_n2_previous_fourni_aucune_donnee_posterieure_a_t():
    s = _serie_regime()
    t = apres(s)
    for prev in (None, "normal", "haut"):
        rw = 0 if prev is None else None
        ref = risk.volatility_regime(s, t, previous=prev, replay_weeks=rw)
        hostile = risk.volatility_regime(avec_futur(s, t), t, previous=prev, replay_weeks=rw)
        assert ref.value == hostile.value and ref.meta == hostile.meta
    # t un jour de barre : les barres de t et suivantes sont ignorées
    cut = s.index[-30]
    ref = risk.volatility_regime(s[s.index < cut], cut.date(), previous="haut").value
    assert risk.volatility_regime(s, cut.date(), previous="haut").value == ref


# ======================================================================== N3 : garde-fous
@pytest.mark.parametrize(
    "vol,leve", [(1e-12, True), (1e-5, True), (0.99e-4, True), (1.01e-4, False), (1e-2, False)]
)
def test_n3_sharpe_sortino_bords_de_volatilite(vol, leve):
    s = _alternee(vol)
    t = apres(s)
    # oracle de la volatilité réellement construite
    p = s.to_numpy()[-253:]
    r = p[1:] / p[:-1] - 1
    assert r.std(ddof=1) * SQ252 == pytest.approx(vol, rel=1e-6)
    for f in (finance.sharpe_ratio, finance.sortino_ratio):
        if leve:
            with pytest.raises(DegenerateSeriesError):
                f(s, t, 252, 0.01)
        else:
            assert math.isfinite(f(s, t, 252, 0.01).value)
    # annualized_volatility ne lève jamais : elle rend la valeur
    assert finance.annualized_volatility(s, t, 252).value == pytest.approx(vol, rel=1e-6)


def test_n3_valeur_du_sharpe_au_dessus_du_seuil_oracle():
    s = _alternee(2e-4)
    t = apres(s)
    p = s.to_numpy()[-253:]
    r = p[1:] / p[:-1] - 1
    ann = (p[-1] / p[0]) ** (252 / 252) - 1
    att = (ann - 0.0) / (r.std(ddof=1) * SQ252)
    assert finance.sharpe_ratio(s, t, 252, 0.0).value == pytest.approx(att, rel=1e-9)


@pytest.mark.parametrize(
    "x,leve", [(0.0, True), (0.9e-6, True), (1e-12, True), (1.1e-6, False), (1e-3, False)]
)
def test_n3_calmar_min_abs_drawdown(x, leve):
    # prix plat à 100 puis une baisse unique de x : perte maximale = x (écrite à la main)
    s = serie([100.0] * 299 + [100.0 * (1 - x)])
    t = apres(s)
    if leve:
        with pytest.raises(DegenerateSeriesError):
            finance.calmar_ratio(s, t, 252)
    else:
        mdd = (100.0 * (1 - x)) / 100.0 - 1
        ann = (1 + mdd) ** (252 / 252) - 1
        assert finance.calmar_ratio(s, t, 252).value == pytest.approx(ann / abs(mdd), rel=1e-9)


def test_n3_constantes_documentees():
    assert finance.MIN_ANNUALIZED_VOLATILITY == 1e-4
    assert finance.SORTINO_MIN_VOLATILITY == finance.MIN_ANNUALIZED_VOLATILITY
    assert finance.MIN_ABS_DRAWDOWN == 1e-6


def test_n3_sharpe_glissant_nan_sous_le_seuil_valeur_au_dessus_oracle_pandas():
    # 4 régimes consécutifs : plat, vol 5e-5 (< seuil), vol 3e-4, vol 5e-2 (annualisées)
    rng = np.random.default_rng(8)
    z = rng.standard_normal(400)
    z = (z - z.mean()) / z.std(ddof=1)
    r = np.concatenate(
        [np.zeros(120), z[:120] * 5e-5 / SQ252, z[120:240] * 3e-4 / SQ252, z[240:] * 5e-2 / SQ252]
    )
    s = depuis_rendements(r)
    t = apres(s)
    w = 63
    got = finance.rolling_sharpe(s, t, w, 0.01).value
    ret = s.pct_change()
    ecart = ret.rolling(w).std(ddof=1)
    rfd = 1.01 ** (1 / 252) - 1
    att = ((ret.rolling(w).mean() - rfd) / ecart).where(ecart * SQ252 >= 1e-4).iloc[w:]
    pd.testing.assert_series_equal(got, att.rename("rolling_sharpe"), rtol=1e-9, check_freq=False)
    assert got.isna().any() and got.notna().any()
    # une fenêtre entièrement dans la zone plate : NaN ; entièrement dans la zone 5e-5 : NaN
    assert got.loc[s.index[100]] != got.loc[s.index[100]]
    assert got.loc[s.index[200]] != got.loc[s.index[200]]
    assert math.isfinite(got.loc[s.index[330]]) and math.isfinite(got.loc[s.index[395]])
    # aucune valeur infinie
    assert not np.isinf(got.dropna()).any()


def test_n3_valuation_summary_marque_les_ratios_refuses_pas_de_nombre():
    s = serie([100.0] * 300)
    out = momentum.valuation_summary(s, apres(s), 0.02).value
    for k in ("sharpe", "sortino", "calmar"):
        assert k in out["manquants"] and k not in out["valeurs"]
    assert out["valeurs"]["volatilite_annualisee"] == 0.0  # une mesure, pas un ratio


# ======================================================================== N4 / N5 : sources
def _panel_vix(n=900):
    p = pd.DataFrame({"A": marche_aleatoire(n, 31), "B": marche_aleatoire(n, 32)})
    d = p.index[-1]
    vix = pd.DataFrame(
        {
            "date": [d - timedelta(days=2), d],
            "value": [18.0, 22.0],
            "available_from": [d - timedelta(days=1), d + timedelta(days=0)],
        }
    )
    return p, vix


def test_n4_une_source_par_actif_regime_et_vix_avec_fenetres_exactes():
    p, vix = _panel_vix()
    t = apres(p)
    res = risk.risk_report(p, p["A"], t, vix=vix)
    rep = res.value
    sources = rep.sources
    assert [m.series for m in sources] == ["A", "B", "A", "vix"]
    ids = [m.source_id for m in sources]
    assert len(set(ids)) == len(ids)  # identifiants uniques (le régime « A » diffère par l'outil)
    n_tail = max(156 * 5 + 21 + 2, 253)  # 803 observations par actif
    for m in sources[:2]:
        assert m.n_obs == n_tail
        assert m.window_start == p.index[-n_tail].date() and m.last_data_date == p.index[-1].date()
    reg = sources[2]
    assert reg.tool == "volatility_regime" and reg.last_data_date == p.index[-1].date()
    n_reg = min(len(p), (156 + 52) * 5 + 21 + 2)
    assert reg.n_obs == n_reg and reg.window_start == p.index[-n_reg].date()
    v = sources[3]
    assert v.n_obs == 1 and v.last_data_date == vix["date"].iloc[-1].date()  # connue : 22,0 ?
    # méta globale : somme des n_obs, fenêtre englobante
    assert res.meta.n_obs == sum(m.n_obs for m in sources)
    assert res.meta.window_start == min(m.window_start for m in sources)
    assert res.meta.last_data_date == max(m.last_data_date for m in sources)


def test_n5_data_instant_aware_utc_anterieur_a_t_extrait_borne_et_lisible():
    p, vix = _panel_vix()
    t = apres(p)
    rep = risk.risk_report(p, p["A"], t, vix=vix).value
    for m in rep.sources:
        di = m.data_instant
        assert di is not None and di.tzinfo is not None and di.utcoffset() == timedelta(0)
        assert di.tzinfo == UTC
        assert di < pd.Timestamp(t).to_pydatetime().replace(tzinfo=UTC)
        assert di.hour == di.minute == di.second == 0
        assert (di.year, di.month, di.day) == (
            m.last_data_date.year,
            m.last_data_date.month,
            m.last_data_date.day,
        )
    res = finance.sharpe_ratio(p["A"], t, 252, 0.02)
    ex = res.extrait
    assert len(ex) <= 500 and "sharpe_ratio" in ex and "valeur =" in ex and "sans unité" in ex
    assert f"t={t.isoformat()}" in ex
    # le nombre cité est celui de la valeur (6 chiffres significatifs)
    assert f"{res.value:.6g}" in ex


def test_n5_extrait_tronque_a_500_avec_ellipse_pour_les_grosses_sorties():
    p = marche_aleatoire(900, 3)
    res = momentum.valuation_summary(p, apres(p), 0.02)
    ex = res.extrait
    assert len(ex) <= 500
    long = base.ToolResult({f"cle_numero_{i}": 1.23456789 * i for i in range(200)}, res.meta)
    assert len(long.extrait) <= 500
    big = base.ToolResult(1.0, base.ToolMeta("x" * 600, "1", date(2024, 1, 1), None, None, 0))
    assert len(big.extrait) == 500 and big.extrait.endswith("…")


def test_n5_source_id_stable_distinct_selon_parametres_et_caracteres_sains():
    p = marche_aleatoire(900, 3).rename("500.PA")
    t = apres(p)
    a = finance.sharpe_ratio(p, t, 252, 0.01).meta
    b = finance.sharpe_ratio(p, t, 252, 0.01).meta
    c = finance.sharpe_ratio(p, t, 252, 0.02).meta  # mêmes dates, autre taux sans risque
    d = finance.sharpe_ratio(p, t, 126, 0.01).meta
    assert a.source_id == b.source_id
    assert len({a.source_id, c.source_id, d.source_id}) == 3
    assert re.fullmatch(r"[A-Za-z0-9_.:\-#]+", a.source_id), a.source_id
    assert a.source_id.startswith("sharpe_ratio:500.PA:") and a.source_id.endswith(
        f"v{base.TOOL_VERSION}#" + a.source_id.split("#")[1]
    )
    # deux séries différentes aux mêmes dates : identifiants différents
    q = marche_aleatoire(900, 4).rename("SPY")
    assert finance.sharpe_ratio(q, t, 252, 0.01).meta.source_id != a.source_id


def test_n5_source_id_np_float64_et_float_donnent_le_meme_identifiant():
    """Un taux sans risque lu d'un tableau numpy (np.float64) ne doit pas changer l'identifiant."""
    p = marche_aleatoire(900, 3).rename("A")
    t = apres(p)
    ident_float = finance.sharpe_ratio(p, t, 252, 0.0123).meta.source_id
    ident_np = finance.sharpe_ratio(p, t, 252, np.float64(0.0123)).meta.source_id
    assert ident_float == ident_np


def test_n5_deterministe_entre_processus_pythonhashseed_differents():
    code = textwrap.dedent(
        """
        import sys; sys.path.insert(0, %r)
        import numpy as np, pandas as pd
        from tools_helpers import marche_aleatoire, apres
        from amundi_agentic.tools import risk, finance
        p = pd.DataFrame({"A": marche_aleatoire(900, 31), "B": marche_aleatoire(900, 32)})
        t = apres(p)
        rep = risk.risk_report(p, p["A"], t).value
        print([m.source_id for m in rep.sources])
        print(finance.sharpe_ratio(p["A"].rename("A"), t, 252, 0.01).extrait)
        """
    ) % str(Path(__file__).parent)
    sorties = []
    for graine in ("1", "2", "12345"):
        env = {"PYTHONHASHSEED": graine, "PATH": "/usr/bin:/bin", **_ENV_HERITE}
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
        )
        sorties.append(out.stdout)
    assert sorties[0] == sorties[1] == sorties[2] and sorties[0].strip()


def test_n5_table_units_complete_pour_chaque_outil_du_code():
    src = Path(base.__file__).parent
    noms = set()
    for f in src.glob("*.py"):
        noms |= set(re.findall(r"make_meta\(\s*\"(\w+)\"", f.read_text(encoding="utf-8")))
    assert {
        "sharpe_ratio",
        "risk_report",
        "volatility_regime",
        "macro_regime",
        "risk_free_annual",
    } <= noms
    manquants = noms - set(base.UNITS)
    assert not manquants, f"outils sans unité : {sorted(manquants)}"
    assert all(isinstance(u, str) and u for u in base.UNITS.values())
    # et la méta de chaque outil exécuté porte bien une unité
    p = marche_aleatoire(900, 5).rename("A")
    t = apres(p)
    df = pd.DataFrame({"A": p, "B": marche_aleatoire(900, 6)})
    for r in (
        finance.cumulative_return(p, t, 63),
        finance.rolling_sharpe(p, t, 63),
        momentum.momentum(p, t, 3),
        momentum.trend_vs_sma(p, t),
        risk.ewma_volatility(p, t),
        risk.historical_var(p, t),
        risk.correlation_matrix(df, t),
        risk.volatility_regime(p, t),
        risk.risk_report(df, p, t),
    ):
        assert r.meta.unit, r.meta.tool


def test_n5_meta_et_sources_serialisables_en_json():
    p, vix = _panel_vix()
    t = apres(p)
    res = risk.risk_report(p, p["A"], t, vix=vix, previous_regime=None, replay_weeks=None)
    for m in [res.meta, *res.value.sources]:
        d = json.loads(json.dumps(m.to_dict()))
        assert d["source_id"] == m.source_id and d["unit"] == m.unit and d["series"] == m.series
    # tous les outils : méta sérialisable, y compris avec des paramètres numpy
    s = p["A"].rename("A")
    for r in (
        finance.sharpe_ratio(s, t, 252, np.float64(0.01)),
        finance.max_drawdown(s, t),
        momentum.momentum(s, t, 6),
        risk.historical_cvar(s, t, 252, np.float64(0.95)),
        risk.volatility_regime(s, t, previous="haut"),
        risk.correlation_matrix(p, t),
    ):
        json.dumps(r.meta.to_dict())


# ======================================================================== N6 : âge du PIB
def _pib_et_cpi(derniere_obs: pd.Timestamp):
    qd = pd.date_range("2022-01-01", derniere_obs, freq="QS")
    gdp = pd.DataFrame(
        {
            "date": qd,
            "value": 100.0 * 1.03 ** (np.arange(len(qd)) / 4),
            "available_from": qd + pd.Timedelta(days=30),
        }
    )
    md = pd.date_range("2022-01-01", "2026-12-01", freq="MS")
    cpi = pd.DataFrame(
        {
            "date": md,
            "value": 100.0 * 1.03 ** (np.arange(len(md)) / 12),
            "available_from": md + pd.Timedelta(days=15),
        }
    )
    return {"fred:GDPC1": gdp, "fred:CPIAUCSL": cpi}


@pytest.mark.parametrize(
    "age,present", [(205, True), (211, True), (239, True), (240, True), (241, False), (300, False)]
)
def test_n6_age_du_pib_trimestriel(age, present):
    derniere = pd.Timestamp("2024-01-01")
    series = _pib_et_cpi(derniere)
    t = (derniere + pd.Timedelta(days=age)).date()
    out = macro_regime(series, t).value
    assert ("croissance_pib_yoy" in out.indicateurs) is present
    if not present:
        assert "croissance_pib_yoy" in out.manquants and out.quadrant is None
        assert (
            "241" in out.manquants["croissance_pib_yoy"]
            or "jours" in str(out.manquants["croissance_pib_yoy"])
            or "j," in out.manquants["croissance_pib_yoy"]
        )
    assert macro_regime(series, t).value.seuils["max_age_days"]["trimestriel"] == 240


# ==================================================================== N7 : agrégation par classe
def _agg(**kw):
    return risk.aggregate_alerts_by_class(**kw)


def test_n7_pire_alerte_responsables_et_tri():
    alertes = {
        "Z.PA": "moderee",
        "A.PA": "elevee",
        "M.PA": "elevee",
        "B.PA": "aucune",
        "C": "aucune",
    }
    classes = {"Z.PA": "x", "A.PA": "x", "M.PA": "x", "B.PA": "y", "C": "y"}
    out = risk.aggregate_alerts_by_class(alertes, classes)
    assert list(out) == ["x", "y"]  # classes triées
    x, y = out["x"], out["y"]
    assert x.alerte == "elevee" and x.responsables == ("A.PA", "M.PA")  # triés, ex aequo gardés
    assert x.actifs == ("A.PA", "M.PA", "Z.PA") and x.indisponibles == ()
    assert y.alerte == "aucune" and y.responsables == () and y.actifs == ("B.PA", "C")
    # déterminisme : ordre d'insertion sans effet
    inv = risk.aggregate_alerts_by_class(
        dict(reversed(list(alertes.items()))), dict(reversed(list(classes.items())))
    )
    assert inv == out and list(inv) == list(out)


def test_n7_indisponible_listee_sans_abaisser_la_classe():
    alertes = {"A": "elevee", "B": "aucune"}
    classes = {"A": "x", "B": "x", "C": "x", "D": "y"}
    out = risk.aggregate_alerts_by_class(alertes, classes, indisponibles=["C", "D", "C"])
    assert out["x"].alerte == "elevee" and out["x"].indisponibles == ("C",)
    assert out["x"].actifs == ("A", "B")
    # la même classe sans l'indisponible a la même alerte (non abaissée, non relevée)
    sans = risk.aggregate_alerts_by_class(alertes, classes)
    assert sans["x"].alerte == out["x"].alerte
    # classe sans aucune alerte calculable : alerte None, jamais « aucune » par défaut
    assert out["y"].alerte is None and out["y"].actifs == () and out["y"].indisponibles == ("D",)
    assert out["y"].responsables == ()


def test_n7_erreurs_explicites():
    with pytest.raises(ToolError):
        risk.aggregate_alerts_by_class({"A": "critique"}, {"A": "x"})  # niveau inconnu
    with pytest.raises(ToolError):
        risk.aggregate_alerts_by_class({"A": "elevee"}, {})  # actif sans classe
    with pytest.raises(ToolError):
        risk.aggregate_alerts_by_class({"A": "aucune"}, {"A": "x"}, indisponibles=["Q"])
    with pytest.raises(ToolError):
        risk.aggregate_alerts_by_class({"A": None}, {"A": "x"})  # type: ignore[dict-item]
    assert risk.aggregate_alerts_by_class({}, {}) == {}


def test_n7_branchement_sur_risk_report_cles_techniques_a_filtrer():
    """`RiskReport.indisponibles` peut contenir `__regime__` et `__vix__` (pas des actifs) : les
    passer tels quels à l'agrégateur lève ToolError. L'appelant doit les filtrer ; le test le
    documente pour que l'agent Risque ne tombe pas dans le piège."""
    p = pd.DataFrame({"A": marche_aleatoire(900, 31), "B": marche_aleatoire(300, 32)})
    p.loc[p.index[-3], "B"] = np.nan
    rep = risk.risk_report(p, p["A"].iloc[:300], apres(p)).value  # benchmark trop court
    assert "__regime__" in rep.indisponibles and "B" in rep.indisponibles
    classes = {"A": "x", "B": "x"}
    with pytest.raises(ToolError):
        risk.aggregate_alerts_by_class(rep.alertes, classes, rep.indisponibles)
    actifs = [k for k in rep.indisponibles if not k.startswith("__")]
    out = risk.aggregate_alerts_by_class(rep.alertes, classes, actifs)
    assert out["x"].indisponibles == ("B",)


# ======================================================================== N4 : temps de calcul
def test_n2_cout_du_repli_par_rejeu_de_52_semaines_raisonnable():
    s = marche_aleatoire(1500, 9)
    t = apres(s)
    risk.volatility_regime(s, t)  # échauffement
    debut = time.perf_counter()
    for _ in range(5):
        risk.volatility_regime(s, t)
    moyen = (time.perf_counter() - debut) / 5
    p = pd.DataFrame({k: marche_aleatoire(1500, 20 + i) for i, k in enumerate("ABCDEFGHIJK")})
    debut = time.perf_counter()
    risk.risk_report(p, p["A"], t)
    rapport = time.perf_counter() - debut
    print(
        f"régime (rejeu 52) : {moyen * 1e3:.1f} ms ; risk_report 11 actifs : {rapport * 1e3:.0f} ms"
    )
    assert moyen < 0.5 and rapport < 3.0  # marge large : mesure, pas micro-benchmark


def test_n5_meta_macro_regime_serialisable_et_sourcee():
    series = _pib_et_cpi(pd.Timestamp("2024-01-01"))
    res = macro_regime(series, date(2024, 6, 1))
    d = json.loads(json.dumps(res.meta.to_dict()))
    assert d["unit"] and d["source_id"].startswith("macro_regime:")
    assert res.meta.data_instant is not None and res.meta.data_instant.tzinfo is not None
