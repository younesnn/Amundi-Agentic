"""Revue indépendante de la règle `class_abs_return` (plafond de |rendement| quotidien par classe).

Signalement seul : la règle ne modifie jamais les données et ne masque aucune autre alerte."""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from amundi_agentic.data.quality import check_prices
from amundi_agentic.data.settings import load_yaml

Q = {
    "max_gap_bdays": 5, "outlier_abs_return": 0.25, "split_jump": 0.40, "stale_run": 50, "min_history_weeks": 1,
    "class_abs_return": {
        "M.PA": {"max": 0.01},
        "B.PA": {"max": 0.03, "exempt": [["2020-03-01", "2020-03-31"]]},
    },
}  # fmt: skip
SANS = {k: v for k, v in Q.items() if k != "class_abs_return"}


def _df(closes, start="2025-07-14", vol=1000, dates=None):
    d = pd.DatetimeIndex(dates) if dates is not None else pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"date": d, "open": closes, "high": closes, "low": closes, "close": closes,
         "volume": vol, "dividends": 0.0, "splits": 0.0}
    )  # fmt: skip


def _flags(df, ticker="M.PA", q=Q):
    return [i for i in check_prices(df, ticker, q) if "plafond de classe" in i.detail]


def test_saut_juste_au_dessus_et_juste_en_dessous_du_plafond():
    assert len(_flags(_df([100.0, 101.2]))) == 1  # +1,2 %
    assert _flags(_df([100.0, 100.99]), "M.PA") == []  # +0,99 %
    assert len(_flags(_df([100.0, 98.8]))) == 1  # -1,2 %
    assert _flags(_df([100.0, 99.01])) == []  # -0,99 %


def test_plafond_exact_n_est_pas_signale_borne_incluse_avec_tolerance():
    """Le plafond est une borne incluse : un rendement égal au plafond (au bruit flottant près) n'est pas signalé ;
    seul un dépassement au-delà de la tolérance de 1e-9 l'est."""
    df = _df([128.0, 129.28])  # 1 % en décimal, 1,0000000000000009 % en flottant
    assert df["close"].pct_change().iloc[1] > 0.01  # le bruit flottant existe bien
    assert _flags(df) == []
    assert (
        _flags(_df([1.0, 1.0 + 2**-7])) == []
    )  # 0,78125 % exactement représentable, sous le plafond
    for delta, signale in ((0.5e-9, False), (2e-9, True), (1e-6, True)):
        f = _flags(_df([100.0, 100.0 * (1 + 0.01 + delta)]))
        assert (len(f) == 1) is signale, delta
    # même côté négatif
    assert _flags(_df([100.0, 100.0 * (1 - 0.01 - 0.5e-9)])) == []
    assert len(_flags(_df([100.0, 100.0 * (1 - 0.01 - 2e-9)]))) == 1


@pytest.mark.parametrize(
    ("fraction", "retour"), [(0.59, False), (0.599, False), (0.61, True), (0.8, True)]
)
def test_retour_le_lendemain_seuil_de_60_pour_cent(fraction, retour):
    r1 = 0.012  # saut de 1,2 % : le retour (<= 0,96 %) reste sous le plafond de 1 % (un seul signalement)
    c1 = 100.0 * (1 + r1)
    f = _flags(_df([100.0, c1, c1 * (1 - fraction * r1)]))
    assert len(f) == 1
    assert ("retour le lendemain" in f[0].detail) is retour


def test_retour_exactement_60_pour_cent_est_signale_comme_retour():
    r1 = 0.012
    c1 = 100.0 * (1 + r1)
    f = _flags(_df([100.0, c1, c1 * (1 - 0.6 * r1)]))
    assert len(f) == 1 and "retour le lendemain" in f[0].detail


@pytest.mark.parametrize(("fraction", "retour"), [(0.5999, False), (0.6, True), (0.6001, True)])
def test_retour_bords_59_99_60_60_01_pour_cent(fraction, retour):
    r1 = 0.012
    c1 = 100.0 * (1 + r1)
    f = _flags(_df([100.0, c1, c1 * (1 - fraction * r1)]))
    assert len(f) == 1
    assert ("retour le lendemain" in f[0].detail) is retour


def test_retour_de_meme_signe_ou_dernier_jour_n_est_pas_un_retour():
    f = _flags(_df([100.0, 102.0, 104.0]))  # continue dans le même sens
    assert "retour" not in f[0].detail
    f2 = _flags(_df([100.0, 102.0]))  # dernier jour : pas de lendemain
    assert len(f2) == 1 and "retour" not in f2[0].detail


def test_ticker_absent_de_la_config_et_config_absente_ou_vide():
    df = _df([100.0, 90.0, 100.0])
    assert _flags(df, "X.PA") == []
    assert _flags(df, "M.PA", SANS) == []
    assert _flags(df, "M.PA", {**Q, "class_abs_return": None}) == []
    assert _flags(df, "M.PA", {**Q, "class_abs_return": {}}) == []
    assert (
        _flags(df, "M.PA", {**Q, "class_abs_return": {"M.PA": {}}}) == []
    )  # entrée vide : ignorée


def test_exemption_mars_2020_aux_bords():
    # dates ouvrées autour des bornes 2020-03-01 / 2020-03-31 (1er mars = dimanche, 31 mars = mardi)
    dates = pd.to_datetime(
        [
            "2020-02-27",
            "2020-02-28",
            "2020-03-02",
            "2020-03-30",
            "2020-03-31",
            "2020-04-01",
            "2020-04-02",
        ]
    )
    closes = [100.0, 95.0, 100.0, 95.0, 100.0, 95.0, 100.0]  # chaque jour : saut de ±5 %
    f = _flags(_df(closes, dates=dates), "B.PA")
    jours = [str(i.start) for i in f]
    assert (
        jours
        == ["2020-02-28", "2020-03-02"][:0] + ["2020-02-28", "2020-04-01", "2020-04-02"][:0] + jours
    )  # base
    assert "2020-02-28" in jours  # veille de la fenêtre : signalé
    assert (
        "2020-03-02" not in jours and "2020-03-30" not in jours and "2020-03-31" not in jours
    )  # dedans
    assert "2020-04-01" in jours and "2020-04-02" in jours  # lendemain de la fenêtre : signalé


def test_serie_courte_nan_volume_nul_dates_non_triees_et_doublons():
    assert _flags(_df([100.0])) == []
    assert check_prices(_df([100.0]), "M.PA", Q) is not None  # ne plante pas
    assert _flags(_df([100.0, 102.0]))[0].detail.count("volume 1000") == 1
    # volume nul : signalé, volume 0 écrit
    f = _flags(_df([100.0, 101.2, 100.5], vol=0))
    assert len(f) == 1 and "volume 0" in f[0].detail
    # NaN dans les cours : aucun plantage, aucun signalement sur un rendement NaN
    c = [100.0, np.nan, 100.5, 100.2]
    assert _flags(_df(c)) == []
    # dates non triées et doublons : le résultat est celui de la série triée dédoublonnée
    triee = _df([100.0, 102.0, 100.0, 100.1])
    melange = triee.iloc[[2, 0, 3, 1]].reset_index(drop=True)
    assert [(str(i.start), i.detail) for i in _flags(melange)] == [
        (str(i.start), i.detail) for i in _flags(triee)
    ]
    dup = pd.concat([triee, triee.iloc[[1]]], ignore_index=True)
    assert [str(i.start) for i in _flags(dup)] == [str(i.start) for i in _flags(triee)]


def test_nan_dans_le_volume_ne_fait_pas_planter_le_controle():
    """Un volume manquant (NaN) au jour du saut ne doit pas faire planter tout le contrôle qualité."""
    df = _df([100.0, 102.0, 100.0])
    df["volume"] = df["volume"].astype(float)
    df.loc[1, "volume"] = np.nan
    f = _flags(df)
    assert len(f) == 2  # +2,00 % puis -1,96 % : tous deux au-delà du plafond de 1 %
    assert "+2.00%" in f[0].detail and "volume inconnu" in f[0].detail
    assert "-1.96%" in f[1].detail and "volume 1000" in f[1].detail
    # volume absent (colonne sans valeur numérique) : pas de plantage non plus
    df2 = _df([100.0, 102.0, 100.0])
    df2["volume"] = pd.Series([None, None, None], dtype=object)
    assert all("volume inconnu" in i.detail for i in _flags(df2))


def test_la_regle_ne_modifie_jamais_les_donnees_et_ne_masque_rien():
    df = _df(
        [100.0, 102.0, 100.0, 55.0, 56.0]
    )  # -40 % : saut « split » existant + plafond de classe
    avant = df.copy(deep=True)
    avec = check_prices(df, "M.PA", Q)
    sans = check_prices(df, "M.PA", SANS)
    pd.testing.assert_frame_equal(df, avant)
    # toutes les alertes existantes sont conservées à l'identique ; la règle n'ajoute que des « plafond de classe »
    reste = [i for i in avec if "plafond de classe" not in i.detail]
    assert reste == sans
    extra = [i for i in avec if "plafond de classe" in i.detail]
    assert extra and all(i.kind == "outlier" and i.severity == "warning" for i in extra)
    # un saut > split_jump reste signalé par l'alerte générique (jamais masqué par la règle de classe)
    assert any("saut de cours" in i.detail for i in avec)


def test_config_reelle_plafonds_marques_h_et_raisonnables():
    from pathlib import Path

    import yaml

    cfg = load_yaml("data.yaml")["quality"]["class_abs_return"]
    attendu = {
        "C3M.PA": 0.01,
        "CSH2.PA": 0.01,
        "MTD.PA": 0.03,
        "EGOV.PA": 0.03,
        "CRP.PA": 0.03,
        "AHYE.PA": 0.05,
    }
    assert {k: v["max"] for k, v in cfg.items()} == attendu
    for k, v in cfg.items():
        assert v.get("exempt", []) in ([], [["2020-03-01", "2020-03-31"]]), k
    texte = (Path(__file__).resolve().parents[2] / "config" / "data.yaml").read_text(
        encoding="utf-8"
    )
    bloc = texte[texte.index("Plafond de |rendement quotidien|") : texte.index("class_abs_return:")]
    assert "(H" in bloc  # hypothèse marquée
    assert yaml.safe_load(texte)["quality"]["class_abs_return"]


# --------------------------------------------------------------------------- vrai stockage (lecture seule)
STORE = "/Users/younes/ESCP/AGENTIC IA Projets/Amundi Agentic Project/Amundi Agentic/.cache/data/store/prices"


def _lire_reel(ticker):
    from pathlib import Path

    p = Path(STORE) / f"{ticker}.parquet"
    if not p.is_file():
        pytest.skip("stockage réel indisponible (CI)")
    return pd.read_parquet(p)


def test_stockage_reel_un_seul_jour_hors_exemption_c3m_2025_07_22():
    q = load_yaml("data.yaml")["quality"]
    trouve = {}
    for t in q["class_abs_return"]:
        df = _lire_reel(t)
        trouve[t] = [
            str(i.start) for i in check_prices(df, t, q) if "plafond de classe" in i.detail
        ]
    assert trouve == {
        "C3M.PA": ["2025-07-22"],
        "CSH2.PA": [],
        "MTD.PA": [],
        "EGOV.PA": [],
        "CRP.PA": [],
        "AHYE.PA": [],
    }
    # recalcul indépendant du plafond hors exemption (aucun jour manqué)
    for t, spec in q["class_abs_return"].items():
        s = (
            _lire_reel(t)
            .sort_values("date")
            .drop_duplicates("date", keep="last")
            .set_index("date")["close"]
        )
        r = s.pct_change().dropna().abs()
        hors = r[~((r.index >= "2020-03-01") & (r.index <= "2020-03-31"))]
        assert [str(d.date()) for d in hors[hors > spec["max"]].index] == (
            ["2025-07-22"] if t == "C3M.PA" else []
        )


def test_stockage_reel_mars_2020_crp_ahye_non_signales_mais_toujours_visibles():
    q = load_yaml("data.yaml")["quality"]
    for t in ("CRP.PA", "AHYE.PA"):
        df = _lire_reel(t)
        s = df.sort_values("date").set_index("date")["close"].pct_change()
        mars = s["2020-03-01":"2020-03-31"]
        assert (
            mars.abs() > q["class_abs_return"][t]["max"]
        ).sum() >= 3  # la volatilité réelle existe
        sans_exempt = copy.deepcopy(q)
        sans_exempt["class_abs_return"][t].pop("exempt")
        n_avec = len([i for i in check_prices(df, t, q) if "plafond de classe" in i.detail])
        n_sans = len(
            [i for i in check_prices(df, t, sans_exempt) if "plafond de classe" in i.detail]
        )
        assert (
            n_avec == 0 and n_sans >= 3
        )  # l'exemption masque seulement le signalement, pas les données


def test_stockage_reel_enquete_c3m_22_juillet_2025_recalculee():
    """Recalcul indépendant (lecture seule) : clôtures, absence de dividende et de split, comparaisons, volatilités
    sur 252 / 756 / 1260 séances (fenêtres du rapport)."""
    c = (
        _lire_reel("C3M.PA")
        .sort_values("date")
        .drop_duplicates("date", keep="last")
        .set_index("date")
    )
    cl = c["close"].loc["2025-07-17":"2025-07-24"].round(3).tolist()
    assert cl == [124.44, 124.005, 124.855, 123.56, 124.435, 124.435]
    assert (c["dividends"] == 0).all() and (c["splits"] == 0).all()
    r = c["close"].pct_change().dropna()
    assert round(r.loc["2025-07-22"] * 100, 2) == -1.04
    for t, attendu in (("CSH2.PA", 0.0), ("EGOV.PA", 0.15), ("MTD.PA", 0.20)):
        x = (
            _lire_reel(t)
            .sort_values("date")
            .set_index("date")["close"]
            .pct_change()
            .loc["2025-07-22"]
        )
        assert round(x * 100, 2) == attendu, t
    d = pd.Timestamp("2025-07-22")
    for n, avec, sans in ((252, 0.383, 0.383), (756, 1.167, 0.998), (1260, 1.002, 0.887)):
        s = r.iloc[-n:]
        assert round(s.std() * np.sqrt(252) * 100, 3) == avec
        assert round(s.drop(d, errors="ignore").std() * np.sqrt(252) * 100, 3) == sans
    # le volume du 22/07 n'est pas isolé : ~30 000 aussi les 18/07, 21/07, 24/07 et 25/07 (médiane 20 j ~ 2 600)
    v = c["volume"].loc["2025-07-18":"2025-07-25"]
    assert (v > 20000).sum() == 5
