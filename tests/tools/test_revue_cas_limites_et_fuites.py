"""Revue indépendante : cas limites d'entrée et attaques de non-fuite (point-in-time, D-038)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from tools_helpers import apres, avec_futur, depuis_rendements, marche_aleatoire, serie

from amundi_agentic.tools import finance, momentum, risk
from amundi_agentic.tools.base import ToolError
from amundi_agentic.tools.macro_regime import macro_regime

BASE = marche_aleatoire(900, graine=21)
T = apres(BASE)

TOUS = {
    "cum": lambda s, t: finance.cumulative_return(s, t, 252),
    "vol": lambda s, t: finance.annualized_volatility(s, t, 252),
    "sharpe": lambda s, t: finance.sharpe_ratio(s, t, 252, 0.02),
    "sortino": lambda s, t: finance.sortino_ratio(s, t, 252, 0.02),
    "mdd": lambda s, t: finance.max_drawdown(s, t, 252),
    "calmar": lambda s, t: finance.calmar_ratio(s, t, 252),
    "roll": lambda s, t: finance.rolling_sharpe(s, t, 63, 0.02),
    "mom12": lambda s, t: momentum.momentum(s, t, 12),
    "mom121": lambda s, t: momentum.momentum_12_1(s, t),
    "sma": lambda s, t: momentum.trend_vs_sma(s, t, 200),
    "summary": lambda s, t: momentum.valuation_summary(s, t, 0.02),
    "rv": lambda s, t: risk.realized_volatility(s, t),
    "ewma": lambda s, t: risk.ewma_volatility(s, t),
    "var": lambda s, t: risk.historical_var(s, t),
    "cvar": lambda s, t: risk.historical_cvar(s, t),
    "regime": lambda s, t: risk.volatility_regime(s, t),
    "regime_rejeu": lambda s, t: risk.volatility_regime(s, t, replay_weeks=30),
}


def _egal(a, b):
    va, vb = a.value, b.value
    if isinstance(va, pd.Series):
        pd.testing.assert_series_equal(va, vb, check_freq=False)
    elif hasattr(va, "regime"):
        assert va == vb
    else:
        assert va == vb
    assert a.meta == b.meta


# ---- fuite : t sur une barre, week-end, férié
@pytest.mark.parametrize("nom", sorted(TOUS))
@pytest.mark.parametrize("decalage", [0, 1, 2, 3])  # t = jour de barre, +1 (sam. ou jour), ...
def test_t_sur_une_barre_ignore_cette_barre_et_les_suivantes(nom, decalage):
    f = TOUS[nom]
    cut = BASE.index[-1]  # dernière barre de la série
    t = (cut + timedelta(days=decalage)).date()
    # série tronquée STRICTEMENT avant t : référence
    ref_serie = BASE[BASE.index < pd.Timestamp(t)]
    attendu = f(ref_serie, t)
    # série complète + barres futures hostiles
    _egal(f(avec_futur(ref_serie, t), t), attendu)
    _egal(f(BASE, t), attendu)  # la vraie barre de t (et suivantes) est tronquée par l'outil


@pytest.mark.parametrize("nom", sorted(TOUS))
def test_t_un_samedi_equivaut_a_t_le_lundi_sans_donnee_du_weekend(nom):
    # barres lun-ven ; t = samedi : dernière barre connue = vendredi, identique à t = dimanche
    idx = BASE.index
    vendredi = [d for d in idx if d.dayofweek == 4][-5]
    s = BASE[BASE.index <= vendredi]
    samedi = (vendredi + timedelta(days=1)).date()
    dimanche = (vendredi + timedelta(days=2)).date()
    a, b = TOUS[nom](s, samedi), TOUS[nom](s, dimanche)
    assert a.value.equals(b.value) if isinstance(a.value, pd.Series) else a.value == b.value
    # le méta indique bien la date de la dernière donnée utilisée : le vendredi (pas t)
    if nom != "mom121":  # 12-1 date sa borne la plus récente (t-1-21), pas la dernière barre
        assert a.meta.last_data_date == vendredi.date()


@pytest.mark.parametrize("nom", sorted(TOUS))
def test_jour_ferie_sans_barre_la_derniere_barre_connue_est_la_veille(nom):
    # trou de 3 jours ouvrés dans la série (férié) : aucune interpolation
    s = BASE.drop(BASE.index[-3:])
    t = BASE.index[-1].date()
    r = TOUS[nom](s, t)
    if nom != "mom121":
        assert r.meta.last_data_date == s.index[-1].date()


# ------------------------------------------------------------ fuite : fenêtre, shift, tri
def test_modifier_la_derniere_barre_connue_change_les_sorties_sensibles():
    """Détecte un `shift(1)` ou une troncature supplémentaire : la barre t-1 doit compter."""
    s2 = BASE.copy()
    s2.iloc[-1] *= 1.05
    for nom in sorted(TOUS):
        if nom in ("cvar", "var", "mom121", "sma", "regime_rejeu", "roll", "ewma", "mdd"):
            continue  # insensibles ou testés plus bas
        a, b = TOUS[nom](BASE, T), TOUS[nom](s2, T)
        assert a.value != b.value, nom
    # perte maximale : la dernière barre compte si elle devient un nouveau creux
    s6 = BASE.copy()
    s6.iloc[-1] = BASE.iloc[-253:].min() * 0.5
    assert finance.max_drawdown(s6, T, 252).value["trough_date"] == s6.index[-1].date()
    # EWMA : poids maximal sur la dernière semaine
    assert risk.ewma_volatility(BASE, T).value != risk.ewma_volatility(s2, T).value
    # Sharpe glissant : la dernière valeur change, les précédentes aussi (fenêtre contenant t-1)
    ra, rb = finance.rolling_sharpe(BASE, T, 63).value, finance.rolling_sharpe(s2, T, 63).value
    assert ra.iloc[-1] != rb.iloc[-1] and ra.iloc[:-2].equals(rb.iloc[:-2])
    # momentum 12-1 : la dernière barre est sautée, mais la barre t-1-21 compte
    s3 = BASE.copy()
    s3.iloc[-1 - 21] *= 1.05
    assert momentum.momentum_12_1(BASE, T).value != momentum.momentum_12_1(s3, T).value
    assert momentum.momentum_12_1(BASE, T).value == momentum.momentum_12_1(s2, T).value
    # SMA 200 : la plus ancienne barre de la fenêtre compte, la 201e non
    s4 = BASE.copy()
    s4.iloc[-200] *= 1.05
    assert momentum.trend_vs_sma(BASE, T, 200).value != momentum.trend_vs_sma(s4, T, 200).value
    s5 = BASE.copy()
    s5.iloc[-201] *= 1.05
    assert momentum.trend_vs_sma(BASE, T, 200).value == momentum.trend_vs_sma(s5, T, 200).value


def test_fenetres_exactes_pas_de_decalage_d_une_seance():
    """La barre juste hors fenêtre (n+2 clôtures en arrière) ne doit jamais compter."""
    n = 63
    base = marche_aleatoire(500, graine=2)
    out = base.copy()
    out.iloc[-(n + 2)] *= 3.0  # une barre de plus que les n+1 de la fenêtre
    t2 = apres(base)
    for f in (
        lambda s: finance.annualized_volatility(s, t2, n),
        lambda s: finance.max_drawdown(s, t2, n),
        lambda s: finance.sortino_ratio(s, t2, n, 0.01),
        lambda s: risk.historical_cvar(s, t2, n),
        lambda s: risk.realized_volatility(s, t2, 21),
    ):
        assert f(base).value == f(out).value
    inn = base.copy()
    inn.iloc[-(n + 1)] *= 1.5  # première clôture de la fenêtre : doit compter
    assert (
        finance.cumulative_return(base, t2, n).value != finance.cumulative_return(inn, t2, n).value
    )


def test_ewma_ne_depend_pas_des_semaines_au_dela_de_260():
    s = marche_aleatoire(2000, graine=4)
    t = apres(s)
    a = risk.ewma_volatility(s, t).value
    s2 = s.copy()
    s2.iloc[: 2000 - 5 * 261 - 1] *= 7.0  # avant la grille retenue
    assert a == risk.ewma_volatility(s2, t).value


def test_regime_ne_depend_pas_du_passe_au_dela_de_la_fenetre_de_reference():
    s = marche_aleatoire(2000, graine=9)
    t = apres(s)
    a = risk.volatility_regime(s, t).value
    s2 = s.copy()
    s2.iloc[:500] *= np.linspace(1, 9, 500)
    assert a == risk.volatility_regime(s2, t).value


def test_regime_rejeu_ne_lit_aucun_futur_et_se_calcule_a_t_moins_1():
    """Le rejeu de la machine à états doit n'utiliser que des clôtures < t à chaque pas."""
    s = marche_aleatoire(1200, graine=13)
    t = apres(s)
    hostile = avec_futur(s, t)
    for rejeu in (0, 10, 52):
        assert (
            risk.volatility_regime(s, t, replay_weeks=rejeu).value
            == risk.volatility_regime(hostile, t, replay_weeks=rejeu).value
        )


def test_regime_depend_de_la_profondeur_de_rejeu_graine_32():
    """Preuve (revue, point 6.3) : le MÊME régime à t vaut « normal » sans rejeu et « haut » avec
    rejeu >= 4 semaines. La profondeur de rejeu doit être gelée dans la configuration
    pré-enregistrée (ou l'état persisté), sinon la reproductibilité est en danger."""
    rng = np.random.default_rng(32)
    r = rng.normal(0, 0.006, 1100)
    r[-70:-40] = rng.normal(0, 0.02, 30)
    r[-40:] = rng.normal(0, 0.0095, 40)
    s = depuis_rendements(r)
    t = apres(s)
    res = {k: risk.volatility_regime(s, t, replay_weeks=k).value.regime for k in (0, 4, 8, 52)}
    assert res[0] == "normal" and res[4] == res[8] == res[52] == "haut"


# ------------------------------------------------------------ entrées invalides
def test_index_avec_fuseau_refuse():
    s = BASE.copy()
    s.index = s.index.tz_localize("Europe/Paris")
    with pytest.raises(ToolError):
        finance.cumulative_return(s, T, 10)


def test_doublons_et_non_trie_refuses_pour_chaque_outil():
    dup = pd.concat([BASE, BASE.iloc[[-5]]]).sort_index(kind="stable")
    desordre = BASE.iloc[::-1]
    for f in TOUS.values():
        for mauvais in (dup, desordre):
            with pytest.raises(ToolError):
                f(mauvais, T)


def test_as_of_datetime_ou_chaine_refuse():
    for bad in (datetime(2024, 1, 1), "2024-01-01", pd.Timestamp("2024-01-01")):
        with pytest.raises(TypeError):
            finance.cumulative_return(BASE, bad, 10)  # type: ignore[arg-type]


def test_nan_isole_dans_la_fenetre_erreur_hors_fenetre_ignore():
    s = BASE.copy()
    s.iloc[-10] = np.nan
    with pytest.raises(ToolError):
        finance.annualized_volatility(s, T, 63)
    with pytest.raises(ToolError):
        risk.realized_volatility(s, T)
    # hors fenêtre de 63 rendements : aucune influence
    s2 = BASE.copy()
    s2.iloc[-100] = np.nan
    assert (
        finance.annualized_volatility(s2, T, 63).value
        == finance.annualized_volatility(BASE, T, 63).value
    )
    # le rolling Sharpe rend ABSENTES (NaN) les fenêtres touchées, jamais remplies
    rs = finance.rolling_sharpe(s, T, 63).value
    assert rs.iloc[-1:].isna().all() and rs.isna().sum() >= 1
    # valuation_summary : indicateur concerné absent, pas de nombre inventé
    out = momentum.valuation_summary(s, T, 0.0).value
    assert "volatilite_annualisee" in out["manquants"]
    assert not any(np.isnan(v) for v in out["valeurs"].values() if isinstance(v, float))


def test_prix_nul_ou_negatif_dans_la_fenetre_erreur_hors_fenetre_tolere():
    for bad in (0.0, -3.0):
        s = BASE.copy()
        s.iloc[-5] = bad
        for nom in ("cum", "vol", "mdd", "rv", "var"):
            with pytest.raises(ToolError):
                TOUS[nom](s, T)
        with pytest.raises(ToolError):
            momentum.trend_vs_sma(s, T, 200)


def test_valeur_aberrante_passee_est_utilisee_telle_quelle_pas_filtree():
    """Un prix aberrant PASSÉ (erreur de données) n'est pas corrigé par les outils : c'est le
    contrôle qualité de la couche data qui doit l'écarter. Documente la responsabilité."""
    s = BASE.copy()
    s.iloc[-30] *= 100
    assert (
        finance.annualized_volatility(s, T, 63).value
        > 10 * finance.annualized_volatility(BASE, T, 63).value
    )


def test_serie_trop_courte_pour_chaque_outil_erreur_explicite():
    court = BASE.iloc[:5]
    t = apres(court)
    for nom in (
        "cum",
        "vol",
        "sharpe",
        "sortino",
        "mdd",
        "calmar",
        "roll",
        "mom12",
        "mom121",
        "sma",
        "rv",
        "ewma",
        "var",
        "cvar",
        "regime",
    ):
        with pytest.raises(ToolError):
            TOUS[nom](court, t)
    # synthèse : ne lève pas, mais liste tous les indicateurs manquants avec leur raison
    out = momentum.valuation_summary(court, t, 0.0).value
    assert out["valeurs"] == {} and len(out["manquants"]) >= 10


def test_serie_vide_et_t_avant_la_premiere_barre():
    vide = BASE.iloc[:0]
    with pytest.raises(ToolError):
        finance.cumulative_return(vide, T, 5)
    with pytest.raises(ToolError):
        finance.cumulative_return(BASE, BASE.index[0].date(), 5)  # rien de connu avant t


def test_fenetre_invalide():
    for w in (0, -3):
        with pytest.raises(ValueError):
            finance.cumulative_return(BASE, T, w)


def test_var_niveau_hors_plage():
    for lvl in (0.3, 1.0, 1.5, float("nan")):
        with pytest.raises(ValueError):
            risk.historical_var(BASE, T, 252, lvl)


# ------------------------------------------------------------ macro : millésimes et disponibilité
def _long(rows):
    return pd.DataFrame(rows, columns=["date", "value", "available_from"]).astype(
        {"date": "datetime64[ns]", "available_from": "datetime64[ns]"}
    )


def _quarters_cpi(t):
    # PIB trimestriel 2022-01-01 .. 2024-04-01 ; CPI mensuel
    qd = pd.date_range("2022-01-01", "2024-04-01", freq="QS")
    gdp = _long(
        [(d, 100.0 * (1.03 ** (i / 4)), d + pd.Timedelta(days=120)) for i, d in enumerate(qd)]
    )
    md = pd.date_range("2022-01-01", "2024-06-01", freq="MS")
    cpi = _long(
        [(d, 100.0 * (1.03 ** (i / 12)), d + pd.Timedelta(days=45)) for i, d in enumerate(md)]
    )
    return {"fred:GDPC1": gdp, "fred:CPIAUCSL": cpi}


def test_macro_disponibilite_egale_a_t_exclue_et_veille_incluse():
    series = _quarters_cpi(None)
    gdp = series["fred:GDPC1"]
    derniere = gdp["available_from"].iloc[-1]
    # t == available_from : NON connue (strictement avant t) ; t = lendemain : connue
    r_egal = macro_regime(series, derniere.date()).value
    r_apres = macro_regime(series, (derniere + pd.Timedelta(days=1)).date()).value
    assert r_egal.dates.get("croissance_pib_yoy") != derniere - pd.Timedelta(days=120)
    assert r_apres.dates["croissance_pib_yoy"] == pd.Timestamp("2024-04-01").date()


def test_macro_millesime_poste_apres_t_jamais_lu_mais_ancien_conserve():
    series = _quarters_cpi(None)
    gdp = series["fred:GDPC1"].copy()
    d = gdp["date"].iloc[-1]
    t = (gdp["available_from"].iloc[-1] + pd.Timedelta(days=10)).date()
    avant = macro_regime(series, t).value.indicateurs["croissance_pib_yoy"]
    # révision publiée APRÈS t : ne doit rien changer
    revise = pd.concat([gdp, _long([(d, 1e6, pd.Timestamp(t) + pd.Timedelta(days=1))])])
    revise2 = pd.concat([gdp, _long([(d, 1e6, pd.Timestamp(t))])])  # publiée exactement à t
    for variante in (revise, revise2):
        s2 = {**series, "fred:GDPC1": variante}
        assert macro_regime(s2, t).value.indicateurs["croissance_pib_yoy"] == avant
    # révision publiée la veille de t : prise en compte
    ok = pd.concat([gdp, _long([(d, 1e6, pd.Timestamp(t) - pd.Timedelta(days=1))])])
    assert (
        macro_regime({**series, "fred:GDPC1": ok}, t).value.indicateurs["croissance_pib_yoy"]
        != avant
    )


def test_macro_observation_future_aberrante_ignoree_toutes_series():
    series = _quarters_cpi(None)
    t = date(2024, 7, 15)
    ref = macro_regime(series, t).value
    futur = pd.Timestamp(t) + pd.Timedelta(days=1)
    hostile = {
        k: pd.concat(
            [
                v,
                _long(
                    [
                        (futur, 1e9, futur),
                        (pd.Timestamp(t), -1e9, futur),
                        (futur + pd.Timedelta(days=40), np.nan, futur),
                    ]
                ),
            ]
        )
        for k, v in series.items()
    }
    out = macro_regime(hostile, t).value
    assert out.indicateurs == ref.indicateurs and out.quadrant == ref.quadrant


def test_macro_observation_a_la_date_t_avec_disponibilite_ancienne_exclue():
    """Une donnée datée t (ou après) est exclue même si available_from est antérieure (ex. date
    de valeur postérieure à la publication : cas d'une prévision) : double garde date ET dispo."""
    from amundi_agentic.tools.base import known_macro

    t = date(2024, 5, 10)
    long = _long(
        [
            (pd.Timestamp("2024-05-09"), 1.0, pd.Timestamp("2024-05-09")),
            (pd.Timestamp("2024-05-10"), 2.0, pd.Timestamp("2024-05-01")),
            (pd.Timestamp("2024-05-11"), 3.0, pd.Timestamp("2024-05-01")),
        ]
    )
    assert list(known_macro(long, t)["value"]) == [1.0]


def test_macro_series_non_triee_ou_doublons_de_date_dernier_millesime_connu():
    series = _quarters_cpi(None)
    t = date(2024, 7, 15)
    ref = macro_regime(series, t).value.indicateurs
    melange = {k: v.sample(frac=1.0, random_state=1) for k, v in series.items()}
    assert macro_regime(melange, t).value.indicateurs == ref


# ------------------------------------------------------------ risk_report / VIX / alertes
def _panel():
    return pd.DataFrame(
        {"A": marche_aleatoire(900, graine=31), "B": marche_aleatoire(900, graine=32)}
    )


def _vix(valeurs, dates, delai=1):
    d = pd.DatetimeIndex(dates)
    return pd.DataFrame(
        {"date": d, "value": valeurs, "available_from": d + pd.Timedelta(days=delai)}
    )


def test_risk_report_vix_est_une_alerte_de_marche_separee_et_ne_change_pas_les_actifs():
    p = _panel()
    t = apres(p)
    bench = p["A"]
    vix_haut = _vix([50.0], [p.index[-1]], delai=0)
    a = risk.risk_report(p, bench, t).value
    b = risk.risk_report(p, bench, t, vix=vix_haut).value
    assert a.alertes == b.alertes and a.alerte_marche is None and b.alerte_marche == "elevee"
    assert b.indicateurs["vix"] == 50.0


def test_risk_report_vix_futur_ou_publie_a_t_ignore():
    p = _panel()
    t = apres(p)
    veille = p.index[-1]
    vix = _vix(
        [20.0, 99.0, 99.0], [veille - pd.Timedelta(days=3), veille, pd.Timestamp(t)], delai=0
    )
    # la ligne de `veille` a available_from == veille < t : connue ; celle de t : exclue
    r = risk.risk_report(p, p["A"], t, vix=vix).value
    assert r.indicateurs["vix"] == 99.0 and r.alerte_marche == "elevee"
    vix2 = _vix([20.0, 99.0], [veille - pd.Timedelta(days=3), pd.Timestamp(t)], delai=0)
    r2 = risk.risk_report(p, p["A"], t, vix=vix2).value
    assert r2.indicateurs["vix"] == 20.0 and r2.alerte_marche == "aucune"


def test_risk_report_actif_incomplet_sans_alerte_par_defaut_jamais_aucune():
    p = _panel()
    p.loc[p.index[-3], "B"] = np.nan
    r = risk.risk_report(p, p["A"], apres(p)).value
    assert "B" not in r.alertes and "B" in r.indisponibles and "A" in r.alertes


def test_risk_report_future_n_influence_pas():
    p = _panel()
    t = apres(p)
    hostile = pd.concat(
        [
            p,
            pd.DataFrame(
                {"A": [1e6, np.nan], "B": [-1.0, 1e-3]},
                index=pd.DatetimeIndex([pd.Timestamp(t), pd.Timestamp(t) + pd.Timedelta(days=1)]),
            ),
        ]
    )
    assert risk.risk_report(p, p["A"], t).value == risk.risk_report(hostile, p["A"], t).value


def test_risk_report_creux_exactement_10_pourcent_ne_declenche_pas_documente():
    """Cas du flottant : -0,09999999999999998. Série calme avec un creux de 90/100-1."""
    rng = np.random.default_rng(1)
    s = serie(95.0 * (1 + rng.normal(0, 0.002, 900)))
    s.iloc[-100] = 100.0  # plus haut de la fenêtre
    s.iloc[-99:] = 90.0  # prix courant
    p = pd.DataFrame({"A": s})
    r_ = risk.risk_report(p, s, apres(p)).value
    assert r_.indicateurs["creux_courant:A"] == pytest.approx(-0.1)
    assert (90.0 / 100.0 - 1.0) != -0.1  # écart flottant


# ------------------------------------------------------------ mutants survivants (revue)
def test_vix_perime_depasse_le_delai_maximal_et_est_signale():
    p = _panel()
    t = apres(p)
    vieux = _vix([40.0], [p.index[-1] - pd.Timedelta(days=30)], delai=0)
    r = risk.risk_report(p, p["A"], t, vix=vieux).value
    assert r.alerte_marche is None and "__vix__" in r.indisponibles and "vix" not in r.indicateurs
    limite = _vix([30.0], [pd.Timestamp(t) - pd.Timedelta(days=10)], delai=0)
    assert risk.risk_report(p, p["A"], t, vix=limite).value.alerte_marche == "moderee"
    juste_trop = _vix([30.0], [pd.Timestamp(t) - pd.Timedelta(days=11)], delai=0)
    assert risk.risk_report(p, p["A"], t, vix=juste_trop).value.alerte_marche is None


def test_cvar_quantile_sur_valeur_observee_inclut_les_egaux():
    # 21 rendements : le quantile 5 % (position 1,0) est exactement la 2e plus petite valeur
    r = [-0.04, -0.02] + [0.01] * 19
    s = depuis_rendements(r)
    arr = np.array(r)
    q = float(np.quantile(arr, 0.05))
    assert q == pytest.approx(-0.02)
    # moyenne des deux plus petites (<= q) : -0,03 ; une comparaison stricte donnerait -0,04
    assert risk.historical_cvar(s, apres(s), 21, 0.95).value == pytest.approx(0.03)


def test_yoy_macro_point_de_comparaison_trop_ancien_est_absent():
    series = _quarters_cpi(None)
    gdp = series["fred:GDPC1"]
    # à t = 2024-07-15 le dernier PIB connu est celui du 2024-01-01 (publié ~2024-04-30) ;
    # on supprime le trimestre d'il y a un an (2023-01-01) : le plus proche est à 90 j > 10 j
    troue = gdp[gdp["date"] != pd.Timestamp("2023-01-01")]
    out = macro_regime({**series, "fred:GDPC1": troue}, date(2024, 7, 15)).value
    assert "croissance_pib_yoy" not in out.indicateurs and out.quadrant is None
    assert "croissance_pib_yoy" in out.manquants


def test_variation_macro_point_de_comparaison_trop_ancien_est_absente():
    d = pd.bdate_range("2023-01-02", "2024-06-28")
    taux = pd.DataFrame({"date": d, "value": 4.0, "available_from": d + pd.Timedelta(days=1)})
    # trou de 60 jours autour de t - 3 mois
    cible = pd.Timestamp("2024-07-01") - pd.DateOffset(months=3)
    taux = taux[
        (taux["date"] < cible - pd.Timedelta(days=45))
        | (taux["date"] > cible + pd.Timedelta(days=15))
    ]
    out = macro_regime({"fred:DGS10": taux}, date(2024, 7, 1)).value
    assert "taux_10y" in out.indicateurs and "taux_10y_var_3m" not in out.indicateurs
    assert "taux_10y_var_3m" in out.manquants
