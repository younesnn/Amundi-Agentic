"""Contrôle qualité : trous, splits, doublons, aberrations, historique court, devises."""

from __future__ import annotations

import pandas as pd
from data_helpers import prix

from amundi_agentic.data.quality import check_dated_series, check_duplicates, check_prices
from amundi_agentic.data.settings import load_yaml

Q = load_yaml("data.yaml")["quality"]


def kinds(issues, severity=None):
    return [i.kind for i in issues if severity is None or i.severity == severity]


def serie(n=1500):
    dates = pd.bdate_range("2020-01-01", periods=n)
    closes = [100 + 0.1 * i for i in range(n)]
    return dates, closes


def test_serie_propre_sans_anomalie():
    d, c = serie()
    assert check_prices(prix(d, c), "AAA", Q) == []


def test_trou_signale_sans_etre_comble():
    d, c = serie()
    df = prix(d, c).drop(index=range(100, 120)).reset_index(drop=True)
    iss = check_prices(df, "AAA", Q)
    assert kinds(iss) == ["gap"] and iss[0].severity == "warning"
    assert len(df) == 1480  # la série n'est pas modifiée


def test_doublons_signales():
    d, c = serie(50)
    df = pd.concat([prix(d, c), prix(d[:3], c[:3])])
    assert "duplicate" in kinds(check_prices(df, "AAA", Q), "error")


def test_split_declare_info_et_saut_non_explique_avertissement():
    d, c = serie()
    c = list(c)
    for i in range(200, 1500):
        c[i] = c[i] / 2  # chute de 50 % non déclarée
    iss = check_prices(prix(d, c), "AAA", Q)
    assert ("split", "warning") in {(i.kind, i.severity) for i in iss}
    splits = [0.0] * 1500
    splits[200] = 2.0
    iss2 = check_prices(prix(d, c, splits=splits), "AAA", Q)
    assert ("split", "warning") not in {(i.kind, i.severity) for i in iss2}
    assert ("split", "info") in {(i.kind, i.severity) for i in iss2}


def test_valeur_aberrante():
    d, c = serie()
    c[250] = c[250] * 1.30  # +30 % puis retour : deux sauts, sous le seuil de split
    iss = check_prices(prix(d, c), "AAA", Q)
    assert "outlier" in kinds(iss, "warning")


def test_serie_trop_courte_et_cloture_non_positive():
    d, c = serie(50)
    assert "short_history" in kinds(check_prices(prix(d, c), "AAA", Q))
    c[10] = 0.0
    assert "non_positive" in kinds(check_prices(prix(d, c), "AAA", Q), "error")


def test_series_figees():
    d, c = serie()
    for i in range(50, 60):
        c[i] = c[50]
    assert "stale" in kinds(check_prices(prix(d, c), "AAA", Q))


def test_devise_incoherente_signalee():
    d, c = serie()
    iss = check_prices(prix(d, c), "GOLD", Q, meta={"currency": "USD"}, expected_currency="EUR")
    assert "currency" in kinds(iss)


def test_serie_vide_et_series_datees():
    assert kinds(check_prices(pd.DataFrame(), "AAA", Q)) == ["short_history"]
    df = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-03-01"])})
    k = kinds(check_dated_series(df, "s", 10))
    assert "duplicate" in k and "gap" in k
    assert check_duplicates(pd.DataFrame({"a": [1, 1]}), ["a"], "x")


def test_premiere_cotation_avec_fuseau_ne_plante_pas():
    d, c = serie()
    meta = {"currency": "EUR", "first_trade_date": pd.Timestamp("2010-01-01", tz="UTC")}
    iss = check_prices(prix(d, c), "AAA", Q, meta=meta)
    assert any("première cotation" in i.detail for i in iss)


def test_saut_sans_split_avec_pic_de_volume_est_un_avertissement_probablement_reel():
    d, c = serie()
    c = list(c)
    for i in range(700, 1500):
        c[i] = c[i] / 2
    df = prix(d, c)
    df.loc[700, "volume"] = 10000.0  # x10 par rapport à 1000
    iss = [i for i in check_prices(df, "AAA", Q) if i.kind == "split"]
    assert len(iss) == 1 and iss[0].severity == "warning" and "probablement réel" in iss[0].detail
    df.loc[700, "volume"] = 1000.0
    iss = [i for i in check_prices(df, "AAA", Q) if i.kind == "split"]
    assert iss[0].severity == "warning" and "à vérifier" in iss[0].detail
