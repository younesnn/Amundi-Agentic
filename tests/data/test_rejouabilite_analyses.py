"""Rejouabilité (instantanés, manifeste), matrice ESG, liquidité, contrôle croisé, distribution."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest
from data_helpers import prix

from amundi_agentic.data.analysis import (
    DETERMINE,
    INCONNU,
    SUPPOSE,
    composition,
    cross_check,
    esg_matrix,
    liquidity_stats,
)
from amundi_agentic.data.connectors.macro import add_us_business_days, us_business_days
from amundi_agentic.data.connectors.prices import PricesConnector
from amundi_agentic.data.manifest import data_manifest
from amundi_agentic.data.quality import check_prices
from amundi_agentic.data.settings import DataSettings, load_yaml
from amundi_agentic.data.store import ParquetStore, rebuild_snapshots_from_store
from amundi_agentic.data.universe import Universe

# ------------------------------------------------------------------ instantanés


def _horloge(jour: str):
    return lambda: datetime.fromisoformat(jour + "T12:00:00+00:00")


def test_snapshot_append_only_idempotent_et_jamais_ecrase(tmp_path):
    st = ParquetStore(tmp_path / "s", tmp_path / "snap", clock=_horloge("2026-10-01"))
    a = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "close": [10.0]})
    p1 = st.snapshot("prices", "AAA", a)
    assert p1 == st.snapshot("prices", "AAA", a)  # idempotent dans la journée
    b = a.assign(close=11.0)
    p2 = st.snapshot("prices", "AAA", b)  # contenu différent le même jour : nouveau fichier
    assert p2 != p1 and pd.read_parquet(p1)["close"].iloc[0] == 10.0  # l'ancien est intact
    assert len(list((tmp_path / "snap" / "prices" / "2026-10-01").glob("*.parquet"))) == 2


def test_snapshots_desactives_sans_dossier(tmp_path):
    assert ParquetStore(tmp_path).snapshot("x", "y", pd.DataFrame({"a": [1]})) is None


def _frame_yf(dates, closes, splits=None):
    idx = pd.DatetimeIndex(pd.to_datetime(dates)).tz_localize("America/New_York")
    n = len(dates)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": [float(c) for c in closes],
                         "Volume": [1.0] * n, "Dividends": [0.0] * n,
                         "Stock Splits": splits or [0.0] * n}, index=idx)  # fmt: skip


def test_retraitement_ne_detruit_pas_l_ancienne_valeur(tmp_path, cfg):
    """Après un split rétroactif de Yahoo, la valeur d'origine reste retrouvable dans l'instantané de la veille."""
    etat = {"split": False}

    def faux(ticker, start, end):
        if etat["split"]:
            return _frame_yf(
                ["2024-01-02", "2024-01-03", "2024-01-04"], [5, 5.5, 6], [0, 0, 2.0]
            ), {}
        return _frame_yf(["2024-01-02", "2024-01-03"], [10, 11]), {}

    jours = iter(["2026-10-01", "2026-10-02"])
    st1 = ParquetStore(tmp_path / "s", tmp_path / "snap", clock=_horloge("2026-10-01"))
    PricesConnector(
        st1, cfg, tmp_path / "h", fetcher=faux, sleep=lambda x: None, today=date(2024, 1, 4)
    ).update("AAA")
    etat["split"] = True
    st2 = ParquetStore(tmp_path / "s", tmp_path / "snap", clock=_horloge("2026-10-02"))
    r = PricesConnector(
        st2, cfg, tmp_path / "h", fetcher=faux, sleep=lambda x: None, today=date(2024, 1, 5)
    ).update("AAA")
    del jours
    assert r["restated"] is True
    assert st2.read("prices/AAA")["close"].tolist() == [5.0, 5.5, 6.0]  # dérivé : valeur corrigée
    hist = st2.read_snapshots("prices", "AAA")
    veille = hist[hist["snapshot_date"] == "2026-10-01"]
    assert veille["close"].tolist() == [10.0, 11.0]  # valeur d'origine retrouvable
    assert set(hist["snapshot_date"]) == {"2026-10-01", "2026-10-02"}
    assert (hist["origin"] == "collecte").all()


def test_reconstruction_depuis_le_stockage_etiquetee(tmp_path):
    st = ParquetStore(tmp_path / "s", tmp_path / "snap", clock=_horloge("2026-10-03"))
    st.write("prices/AAA", pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "close": [1.0]}))
    st.write("macro/fred/X", pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "value": [1.0]}))
    assert rebuild_snapshots_from_store(st) == {"prices": 1, "macro": 1}
    assert rebuild_snapshots_from_store(st) == {"prices": 1, "macro": 1}  # idempotent
    h = st.read_snapshots("prices", "AAA")
    assert h["origin"].iloc[0] == "reconstruit_depuis_le_stockage" and len(h) == 1


# ------------------------------------------------------------------ manifeste


def _settings_peuple(tmp_path):
    s = DataSettings.load(tmp_path)
    st = ParquetStore(s.store_dir, s.snapshot_dir, clock=_horloge("2026-10-01"))
    st.write("prices/AAA", prix(pd.bdate_range("2024-01-02", periods=5), [1, 2, 3, 4, 5]))
    st.snapshot("prices", "AAA", st.read("prices/AAA"))
    return s, st


def test_manifeste_deterministe_et_sensible_a_un_octet(tmp_path):
    s, st = _settings_peuple(tmp_path)
    m1, m2 = data_manifest(s), data_manifest(s)
    assert m1["manifest_sha256"] == m2["manifest_sha256"]
    sans = lambda m: {k: v for k, v in m.items() if k != "generated_at"}  # noqa: E731
    assert sans(m1) == sans(m2)
    kinds = {d["kind"] for d in m1["datasets"]}
    assert kinds == {"derive", "snapshot"}
    d = next(d for d in m1["datasets"] if d["kind"] == "derive")
    assert d["rows"] == 5 and d["date_min"] and len(d["sha256"]) == 64
    assert set(m1["config_sha256"]) == {
        "data.yaml",
        "universe.yaml",
        "esg.yaml",
        "esg_etf_sources.yaml",
        "esg_etf_sources.lock.json",
    }
    assert {"python", "pandas", "pyarrow", "yfinance", "requests"} <= set(m1["versions"])


def test_hash_sensible_a_un_octet(tmp_path):
    from amundi_agentic.data.manifest import sha256_file

    f = tmp_path / "x.bin"
    f.write_bytes(b"abcdef")
    h1 = sha256_file(f)
    f.write_bytes(b"abcdeg")
    assert sha256_file(f) != h1


def test_manifeste_change_si_un_jeu_change(tmp_path):
    s, st = _settings_peuple(tmp_path)
    avant = data_manifest(s)["manifest_sha256"]
    st.write("prices/AAA", prix(pd.bdate_range("2024-01-02", periods=5), [1, 2, 3, 4, 6]))
    assert data_manifest(s)["manifest_sha256"] != avant


# ------------------------------------------------------------------ matrice ESG


def _records(rows):
    return pd.DataFrame(rows).assign(observed_at=pd.Timestamp("2026-10-02", tz="UTC"))


def test_matrice_esg_trois_etats_et_totaux():
    cfg = load_yaml("esg.yaml")
    rec = _records(
        [
            {"asset_id": "S1", "kind": "stock", "sic": "3571", "notes": ""},
            {
                "asset_id": "S2",
                "kind": "stock",
                "sic": "2111",
                "notes": "vendor_flag:controversial_weapons",
            },
            {"asset_id": "S3", "kind": "stock", "sic": None, "notes": "no_sic"},
            {
                "asset_id": "E1",
                "kind": "etf",
                "sic": None,
                "notes": "basis:paris_aligned_index|not_verified",
            },
            {"asset_id": "E2", "kind": "etf", "sic": None, "notes": "basis:esg_index|not_verified"},
            {
                "asset_id": "E3",
                "kind": "etf",
                "sic": None,
                "notes": "basis:none_known|not_verified",
            },
        ]
    )
    lignes, tot = esg_matrix(rec, cfg["normative_exclusions"], cfg["basis_definitions"])
    par = {r["actif"]: r for r in lignes}
    assert par["S1"]["tobacco"] == SUPPOSE and par["S1"]["controversial_weapons"] == INCONNU
    assert par["S2"]["controversial_weapons"] == DETERMINE  # indicateur fournisseur
    assert par["S3"]["tobacco"] == INCONNU  # SIC absent
    assert par["E1"]["thermal_coal"] == SUPPOSE and par["E1"]["controversial_weapons"] == SUPPOSE
    assert par["E2"]["tobacco"] == INCONNU and par["E3"]["tobacco"] == INCONNU
    assert tot["controversial_weapons"] == {DETERMINE: 1, SUPPOSE: 1, INCONNU: 4}
    assert (
        tot["tous_criteres"][DETERMINE]
        + tot["tous_criteres"][SUPPOSE]
        + tot["tous_criteres"][INCONNU]
        == 18
    )
    assert tot["actifs"] == 6


def test_aucune_regle_sic_pour_les_armes_controversees():
    """Sans indicateur fournisseur, « armes controversées » n'est jamais déterminé pour un titre."""
    cfg = load_yaml("esg.yaml")
    rec = _records(
        [{"asset_id": f"S{i}", "kind": "stock", "sic": "3571", "notes": ""} for i in range(4)]
    )
    _, tot = esg_matrix(rec, cfg["normative_exclusions"], cfg["basis_definitions"])
    assert (
        tot["controversial_weapons"][DETERMINE] == 0 and tot["controversial_weapons"][INCONNU] == 4
    )


# ------------------------------------------------------------------ liquidité, contrôle croisé


def test_liquidite_valeurs_calculees_a_la_main():
    d = pd.DataFrame(
        {"date": pd.to_datetime(["2017-12-29", "2018-01-02", "2018-01-03", "2018-01-04", "2018-01-05"]),
         "volume": [999.0, 10.0, 0.0, 30.0, 20.0], "close": [1.0, 2.0, 2.0, 2.0, 2.0]}
    )  # fmt: skip
    r = liquidity_stats(d, "2018-01-01")
    assert r["jours_depuis"] == 4 and r["valeur_mediane_par_jour"] == pytest.approx(
        30.0
    )  # [20,0,60,40]
    assert r["part_jours_sans_volume"] == 0.25 and r["valeur_p10"] == pytest.approx(6.0)
    assert liquidity_stats(d, "2030-01-01") is None


def test_controle_croise_proxy_parfait_et_proxy_biaise():
    d = pd.bdate_range("2020-01-01", periods=600)
    rng = np.random.default_rng(1)
    usd = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600))), index=d)
    fx = pd.Series(1.1, index=d)
    primaire = usd / 1.1  # même actif, coté en EUR
    r = cross_check(primaire, usd, fx)
    assert (
        r["coef_variation"] == pytest.approx(0.0, abs=1e-12)
        and r["erreur_suivi_hebdo_annualisee"] < 1e-9
    )
    assert r["ratio_moyen"] == pytest.approx(1.0) and abs(r["derive_annuelle"]) < 1e-9
    biaise = primaire * np.exp(np.linspace(0, 0.2, 600))  # dérive de ~8 % par an
    assert cross_check(biaise, usd, fx)["derive_annuelle"] > 0.05
    assert cross_check(primaire.iloc[:50], usd, fx) is None  # recouvrement insuffisant


def test_composition_par_date():
    u = Universe.load()
    prem = {
        "500.PA": pd.Timestamp("2010-06-08"),
        "SPY": pd.Timestamp("1993-01-29"),
        "MTD.PA": pd.Timestamp("2009-01-02"),
    }
    dern = {k: pd.Timestamp("2026-09-30") for k in prem}
    lignes = composition(u, prem, dern)
    us = [r for r in lignes if r["classe"] == "actions_etats_unis"]
    assert "SYNTHÉTIQUE" in us[0]["source"] and us[0]["fin"] == pd.Timestamp("2010-06-07")
    assert us[1]["debut"] == pd.Timestamp("2010-06-08")
    mtd = next(r for r in lignes if r["classe"] == "souverain_euro")
    assert "aucun proxy" in mtd["source"]  # pas de proxy USD pour les taux


# ------------------------------------------------------------------ distribution


def test_distribution_declaree_dist_sans_dividende_est_une_erreur():
    qcfg = load_yaml("data.yaml")["quality"]
    d = pd.bdate_range("2018-01-01", periods=1500)
    df = prix(d, [100 + 0.1 * i for i in range(1500)])
    iss = check_prices(df, "AAA", qcfg, distribution="dist")
    assert any(i.kind == "distribution" and i.severity == "error" for i in iss)
    df.loc[10, "dividends"] = 1.0
    assert not [
        i for i in check_prices(df, "AAA", qcfg, distribution="dist") if i.kind == "distribution"
    ]
    assert any(
        i.severity == "error"
        for i in check_prices(df, "AAA", qcfg, distribution="acc")
        if i.kind == "distribution"
    )
    a_verif = [
        i
        for i in check_prices(df, "AAA", qcfg, distribution="a_verifier")
        if i.kind == "distribution"
    ]
    assert a_verif and a_verif[0].severity == "info"


def test_config_distribution_renseignee_pour_chaque_candidat():
    u = Universe.load()
    for c in u.candidates():
        assert c.distribution in {"acc", "dist", "a_verifier"}, c.ticker
    par = {c.ticker: c.distribution for c in u.candidates()}
    assert par["JPN.PA"] == "dist" and par["GOLD.PA"] == "a_verifier"


# ------------------------------------------------------------------ jours ouvrés vectorisés


def test_jours_ouvres_vectorises_identiques_a_pandas():
    d = pd.Series(
        pd.date_range("2023-12-20", "2024-12-31", freq="D")
    )  # y compris week-ends et fériés
    for n in (1, 2):
        attendu = d + us_business_days(n)
        assert (add_us_business_days(d, n).values == attendu.values).all()


# ------------------------------------------------------------------ creux et composition HY


def _serie(points):
    d = pd.bdate_range("2020-01-01", periods=len(points))
    return pd.Series(points, index=d, dtype=float)


def test_creux_synthetiques_connus():
    from amundi_agentic.data.analysis import drawdown_episodes

    # 100 -> 80 (-20 %, récupéré) ; 120 -> 103,2 (-14 %, non retenu) ; 130 -> 97,5 (-25 %, non récupéré)
    pts = [100, 90, 80, 90, 100, 110, 120, 110, 103.2, 115, 125, 130, 110, 97.5, 100]
    r = drawdown_episodes(_serie(pts), 0.15)
    assert len(r) == 2
    assert r[0]["amplitude"] == pytest.approx(-0.20) and r[0]["recuperation"] is not None
    assert r[0]["pic_prix"] == 100 and r[0]["creux_prix"] == 80
    assert r[1]["amplitude"] == pytest.approx(-0.25) and r[1]["recuperation"] is None
    assert len(drawdown_episodes(_serie(pts), 0.10)) == 3  # le creux de 14 % est retenu à 10 %


def test_table_des_creux_avec_variation_de_taux():
    from amundi_agentic.data.analysis import drawdown_table

    px = _serie([100, 90, 80, 90, 100, 110])
    taux = pd.Series([2.0, 2.5, 3.0, 3.0, 3.0, 3.0], index=px.index)
    t = drawdown_table(px, [str(px.index[0].date())], 0.15, taux)
    assert (
        len(t) == 1
        and t[0]["variation_taux_pb"] == pytest.approx(100.0)
        and t[0]["hausse_des_taux"]
    )
    assert drawdown_table(px, [str(px.index[3].date())], 0.15) == []  # fenêtre après le creux


def test_composition_ne_cite_pas_une_serie_publique_qui_n_existe_pas_avant_l_etf():
    u = Universe.load()
    prem = {"AHYE.PA": pd.Timestamp("2013-09-03"), "C3M.PA": pd.Timestamp("2009-06-22")}
    dern = {k: pd.Timestamp("2026-09-30") for k in prem}
    eur = {"fred:BAMLHE00EHYITRIV": pd.Timestamp("2023-10-02"), "ecb:EONIA": pd.Timestamp("1999-01-04"),
           "ecb:ESTR": pd.Timestamp("2019-10-01")}  # fmt: skip
    lignes = composition(u, prem, dern, eur)
    hy = next(r for r in lignes if r["classe"] == "haut_rendement_euro")
    assert "aucune série EUR publique avant l'ETF" in hy["source"] and "BAML" not in hy["source"]
    mm = next(r for r in lignes if r["classe"] == "monetaire_euro")
    assert "ecb:EONIA" in mm["source"]
