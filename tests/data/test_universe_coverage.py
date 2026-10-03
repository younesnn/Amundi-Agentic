"""Univers, conversion EUR, jonctions, monétaire capitalisé, config sans ticker dans le code, couverture."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from data_helpers import prix

from amundi_agentic.data.coverage import Report
from amundi_agentic.data.settings import DataSettings, load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import (
    Universe,
    convert_to_eur,
    money_market_index,
    parse_constituents_html,
    splice_series,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "amundi_agentic"


def test_univers_charge_depuis_config():
    u = Universe.load()
    assert u.reference_currency == "EUR" and "500.PA" in u.etf_tickers()
    assert len(u.stock_demo_tickers) == 15  # D-029 : environ 15 titres


def test_pas_de_proxy_usd_pour_les_taux():
    """D-011, EX-O2-10 : obligations et monétaire en EUR uniquement, aucun proxy USD."""
    u = Universe.load()
    for nom in ("souverain_euro", "credit_ig_euro", "haut_rendement_euro", "monetaire_euro"):
        assert u.classes[nom].proxy is None, nom
    for nom in (
        "actions_etats_unis",
        "actions_europe",
        "actions_japon",
        "actions_emergents",
        "or",
        "matieres_premieres",
    ):
        assert u.classes[nom].proxy is not None and u.classes[nom].proxy.currency == "USD"


def test_aucun_ticker_dans_le_code():
    """Les tickers vivent dans config/, jamais dans le code de data/."""
    u = Universe.load()
    tickers = set(u.etf_tickers()) | set(u.stock_demo_tickers)
    import re

    for f in (SRC / "data").rglob("*.py"):
        mots = set(
            re.findall(r"[\"']([A-Z0-9]{2,5}(?:\.[A-Z]{1,3})?)[\"']", f.read_text(encoding="utf-8"))
        )
        assert not (mots & tickers), (f, mots & tickers)


def test_conversion_eur_au_cours_bce_connu():
    px = pd.Series(
        [110.0, 55.0, 60.0],
        index=pd.to_datetime(["2024-01-09", "2024-01-10", "2024-01-20"]),
        name="X",
    )
    fx = pd.Series(
        [1.10, 1.10], index=pd.to_datetime(["2024-01-09", "2024-01-09"][:1] + ["2024-01-11"])
    )
    eur, st = convert_to_eur(px, fx, max_stale_days=5)
    assert eur.iloc[0] == pytest.approx(100.0)
    assert eur.iloc[1] == pytest.approx(50.0)  # fixing du 09 reporté (explicite, compté)
    assert np.isnan(eur.iloc[2])  # fixing du 11 : trop ancien (9 jours) -> NaN, pas inventé
    assert st == {"exact_fixing": 1, "stale_fixing_carried": 1, "no_fixing_nan": 1}


def test_conversion_n_utilise_jamais_un_fixing_posterieur():
    px = pd.Series([100.0], index=pd.to_datetime(["2024-01-09"]), name="X")
    fx = pd.Series([2.0], index=pd.to_datetime(["2024-01-10"]))
    eur, st = convert_to_eur(px, fx, 5)
    assert np.isnan(eur.iloc[0]) and st["no_fixing_nan"] == 1


def test_jonction_date_recouvrement_et_ecart_de_suivi():
    d = pd.bdate_range("2020-01-01", periods=300)
    proxy = pd.Series(100 * np.exp(np.cumsum(np.full(300, 0.0004))), index=d)
    primary = proxy.iloc[150:] * 1.5  # même rendements, niveau différent
    sp = splice_series(primary, proxy)
    assert sp.junction_date == d[150] and sp.overlap_days == 150
    assert sp.tracking_error_annualized == pytest.approx(0.0, abs=1e-9)
    assert sp.series.index[0] == d[0] and len(sp.series) == 300
    assert sp.series.pct_change().dropna().round(9).nunique() == 1  # rendements enchaînés sans saut


def test_jonction_recouvrement_insuffisant_signale():
    d = pd.bdate_range("2020-01-01", periods=30)
    sp = splice_series(pd.Series(1.0, index=d[25:]), pd.Series(1.0, index=d[:28]))
    assert sp.tracking_error_annualized is None and "insuffisant" in sp.note


def test_monetaire_capitalise_act_360():
    eonia = pd.Series([3.6, 3.6], index=pd.to_datetime(["2019-09-26", "2019-09-27"]))  # %
    estr = pd.Series([-0.5, -0.5], index=pd.to_datetime(["2019-10-01", "2019-10-02"]))
    idx = money_market_index(eonia, estr)
    # 26->27 : 1 jour à 3,6 % ; 27->01/10 : 4 jours à 3,6 % ; 01->02 : 1 jour à -0,5 %
    attendu = (1 + 0.036 / 360) * (1 + 0.036 * 4 / 360) * (1 - 0.005 / 360)
    assert idx.iloc[-1] == pytest.approx(100 * attendu)
    assert list(idx.index) == list(pd.to_datetime(["2019-09-27", "2019-10-01", "2019-10-02"]))


def test_analyse_du_tableau_de_constituants():
    html = (
        "<table><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr>"
        "<tr><td>AAA</td><td>A</td><td>Information Technology</td></tr>"
        "<tr><td>BRK.B</td><td>B</td><td>Financials</td></tr>"
        "<tr><td>CCC.X</td><td>C</td><td>Information Technology</td></tr></table>"
    )
    assert parse_constituents_html(html, "Information Technology") == ["AAA", "CCC-X"]
    assert parse_constituents_html("<p>rien</p>", "x") == []


# --------------------------------------------------------------------------- couverture


def _peupler(store: ParquetStore):
    d = pd.bdate_range("2020-01-01", periods=1500)
    store.write("prices/500.PA", prix(d, [100 + 0.05 * i for i in range(1500)]))
    store.write(
        "esg/records",
        pd.DataFrame(
            {
                "asset_id": ["AAA", "BBB", "500.PA", "CRP.PA"],
                "kind": ["stock", "stock", "etf", "etf"],
                "score": [20.0, None, None, None],
                "score_source": ["v", None, None, None],
                "exclusions": ["", "tobacco", "", "tobacco|thermal_coal"],
                "exclusion_basis": ["sic", "sic", None, "etf_methodology"],
                "determined": [True, True, False, True],
                "observed_at": pd.to_datetime(["2026-10-02"] * 4, utc=True),
                "sic": ["1", "2", None, None],
                "notes": [""] * 4,
            }
        ),
    )
    store.write(
        "news/items",
        pd.DataFrame(
            {
                "item_id": ["1", "2"],
                "source": ["gdelt", "rss"],
                "published_at": pd.to_datetime(["2026-09-01", "2026-09-20"], utc=True),
                "first_seen_at": pd.to_datetime(["2026-10-01"] * 2, utc=True),
                "title": ["a", "b"],
                "summary": ["", ""],
                "url": ["u1", "u2"],
                "time_semantics": ["seendate", "published"],
                "tags": ["ZS", ""],
            }
        ),
    )


def test_rapport_de_couverture_genere_depuis_le_stockage(tmp_path):
    settings = DataSettings.load(tmp_path)
    store = ParquetStore(settings.store_dir)
    _peupler(store)
    texte, data = Report(settings).build()
    # ESG : 4 actifs, 1 score (25 %), 3 déterminations (75 %), 2 actifs avec exclusion détectée
    g = data["esg"]["global"]
    assert (
        g["actifs"] == 4 and g["part_avec_score"] == 0.25 and g["part_avec_determination"] == 0.75
    )
    assert g["avec_exclusion_detectee"] == 2
    assert "Couverture des données" in texte and "Ne pas éditer à la main" in texte
    # sources absentes dites telles quelles, pas de valeur fabriquée
    assert "indisponible" in texte
    assert data["news"]["total"] == 2
    ligne = next(r for r in data["prices_etf"] if r["ticker"] == "500.PA")
    assert ligne["barres"] == 1500 and ligne["statut"] == "ok"


def test_rapport_sans_donnees_ne_plante_pas_et_le_dit(tmp_path):
    texte, data = Report(DataSettings.load(tmp_path)).build()
    assert "Indisponible" in texte and data["esg"]["actifs"] == 0 and data["news"]["total"] == 0


def test_config_data_et_esg_coherentes():
    cfg, esg = load_yaml("data.yaml"), load_yaml("esg.yaml")
    assert cfg["http"]["sources"]["edgar"]["min_interval_s"] >= 0.1  # <= 10 requêtes/s
    assert cfg["point_in_time"]["timezone"] == "Europe/Paris"
    assert set(esg["normative_exclusions"]) >= {"controversial_weapons", "tobacco", "thermal_coal"}
    for spec in esg["etf_methodology"]["by_ticker"].values():
        assert spec["basis"] in esg["basis_definitions"]
