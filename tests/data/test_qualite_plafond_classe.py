"""Plafond de mouvement journalier par classe d'actifs (signalement seul, jamais de correction)."""

from __future__ import annotations

import pandas as pd

from amundi_agentic.data.quality import check_prices
from amundi_agentic.data.settings import load_yaml

Q = {
    "max_gap_bdays": 5,
    "outlier_abs_return": 0.25,
    "split_jump": 0.40,
    "stale_run": 50,
    "min_history_weeks": 1,
    "class_abs_return": {
        "M.PA": {"max": 0.01},
        "B.PA": {"max": 0.03, "exempt": [["2020-03-01", "2020-03-31"]]},
    },
}


def _serie(closes, start="2025-07-14", vol=1000):
    d = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"date": d, "open": closes, "high": closes, "low": closes, "close": closes,
         "volume": vol, "dividends": 0.0, "splits": 0.0}
    )  # fmt: skip


def _flags(df, ticker):
    return [i for i in check_prices(df, ticker, Q) if "plafond de classe" in i.detail]


def test_saut_monetaire_au_dela_du_plafond_signale_avec_retour_et_donnees_intactes():
    df = _serie([124.4, 124.0, 124.85, 123.56, 124.43, 124.43])
    avant = df.copy()
    f = _flags(df, "M.PA")
    assert [str(i.start) for i in f] == ["2025-07-17"]  # -1,04 % ; 0,69 % < 1 %
    assert f[0].kind == "outlier"
    assert "retour le lendemain" in f[0].detail
    pd.testing.assert_frame_equal(df, avant)  # aucune correction


def test_sous_le_plafond_aucun_signalement_et_ticker_sans_plafond_ignore():
    df = _serie([100.0, 100.5, 100.0, 100.4])
    assert _flags(df, "M.PA") == []
    assert _flags(_serie([100.0, 90.0, 100.0]), "X.PA") == []


def test_fenetre_exemptee_mars_2020_et_hors_fenetre_signale():
    mars = _serie([100.0, 95.0, 100.0], start="2020-03-16")
    assert _flags(mars, "B.PA") == []
    avril = _serie([100.0, 95.0, 96.0], start="2021-03-16")
    f = _flags(avril, "B.PA")
    assert len(f) == 1 and "retour" not in f[0].detail


def test_config_reelle_couvre_les_six_etf_monetaires_et_obligataires():
    cfg = load_yaml("data.yaml")["quality"]["class_abs_return"]
    assert set(cfg) == {"C3M.PA", "CSH2.PA", "MTD.PA", "EGOV.PA", "CRP.PA", "AHYE.PA"}
    assert cfg["C3M.PA"]["max"] == 0.01 and "exempt" not in cfg["C3M.PA"]
