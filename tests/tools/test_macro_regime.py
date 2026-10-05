"""tools/macro_regime.py : indicateurs de régime, données manquantes, absence de fuite.

t = 2024-06-15. Les tableaux ont le format de `DataView.macro_long` (date, value, available_from).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from amundi_agentic.tools import macro_regime as mr

T = date(2024, 6, 15)


def df(lignes) -> pd.DataFrame:
    return pd.DataFrame(
        [(pd.Timestamp(d), v, pd.Timestamp(a)) for d, v, a in lignes],
        columns=["date", "value", "available_from"],
    )


def jeu() -> dict[str, pd.DataFrame]:
    return {
        # PIB réel (niveau) : 1T 2023 = 100 -> 1T 2024 = 103 : +3 % sur un an
        "fred:GDPC1": df(
            [("2023-01-01", 100.0, "2023-04-27"), ("2024-01-01", 103.0, "2024-04-25")]
        ),
        # CPI : mai 2023 = 300 -> mai 2024 = 309 : +3 % sur un an
        "fred:CPIAUCSL": df(
            [("2023-05-01", 300.0, "2023-06-13"), ("2024-05-01", 309.0, "2024-06-12")]
        ),
        "fred:UNRATE": df([("2023-05-01", 3.5, "2023-06-02"), ("2024-05-01", 4.0, "2024-06-07")]),
        "fred:DGS10": df(
            [
                ("2023-06-13", 3.7, "2023-06-14"),
                ("2024-03-13", 4.0, "2024-03-14"),
                ("2024-06-13", 4.5, "2024-06-14"),
            ]
        ),
        "fred:DGS2": df(
            [
                ("2023-06-13", 4.1, "2023-06-14"),
                ("2024-03-13", 4.6, "2024-03-14"),
                ("2024-06-13", 4.9, "2024-06-14"),
            ]
        ),
        "fred:BAMLH0A0HYM2": df(
            [("2024-03-13", 3.0, "2024-03-14"), ("2024-06-13", 3.5, "2024-06-14")]
        ),
        "fred:VIXCLS": df([("2024-03-13", 14.0, "2024-03-14"), ("2024-06-13", 12.5, "2024-06-14")]),
    }


def calc(series=None, **kw):
    return mr.macro_regime(jeu() if series is None else series, T, **kw)


def test_croissance_et_inflation_sur_un_an_et_quadrant():
    v = calc().value
    assert v.indicateurs["croissance_pib_yoy"] == pytest.approx(103 / 100 - 1)
    assert v.indicateurs["inflation_ipc_yoy"] == pytest.approx(309 / 300 - 1)
    assert v.quadrant == "surchauffe"  # 3 % >= 2 % et 3 % >= 2 %
    assert v.dates["croissance_pib_yoy"] == date(2024, 1, 1)


@pytest.mark.parametrize(
    ("croissance", "inflation", "attendu"),
    [
        (0.03, 0.01, "expansion_desinflation"),
        (0.03, 0.03, "surchauffe"),
        (0.00, 0.04, "stagflation"),
        (0.00, 0.01, "ralentissement"),
        (0.02, 0.02, "surchauffe"),  # seuils atteints : >= (H1)
    ],
)
def test_quatre_quadrants(croissance, inflation, attendu):
    s = jeu()
    s["fred:GDPC1"] = df(
        [
            ("2023-01-01", 100.0, "2023-04-27"),
            ("2024-01-01", 100.0 * (1 + croissance), "2024-04-25"),
        ]
    )
    s["fred:CPIAUCSL"] = df(
        [("2023-05-01", 200.0, "2023-06-13"), ("2024-05-01", 200.0 * (1 + inflation), "2024-06-12")]
    )
    assert calc(s).value.quadrant == attendu


def test_chomage_taux_pentes_ecarts_en_decimal():
    v = calc().value.indicateurs
    assert v["chomage"] == pytest.approx(0.04)
    assert v["chomage_var_12m"] == pytest.approx((4.0 - 3.5) / 100)
    assert v["taux_10y"] == pytest.approx(0.045)
    assert v["taux_10y_var_3m"] == pytest.approx((4.5 - 4.0) / 100)
    assert v["taux_10y_var_12m"] == pytest.approx((4.5 - 3.7) / 100)
    # T10Y2Y absent : pente = DGS10 - DGS2 à la même date : -0,4 ; il y a 3 mois -0,6 ; 12 mois -0,4
    assert v["pente_us_10y_2y"] == pytest.approx((4.5 - 4.9) / 100)
    assert v["pente_us_10y_2y_var_3m"] == pytest.approx(((4.5 - 4.9) - (4.0 - 4.6)) / 100)
    assert v["pente_us_10y_2y_var_12m"] == pytest.approx(((4.5 - 4.9) - (3.7 - 4.1)) / 100)
    assert v["ecart_credit_hy"] == pytest.approx(0.035)
    assert v["ecart_credit_hy_var_3m"] == pytest.approx(0.005)
    assert v["vix"] == 12.5 and v["vix_var_3m"] == pytest.approx(-1.5)
    assert calc().value.drapeaux["courbe_inversee_us"] is True


def test_pente_t10y2y_prioritaire_quand_presente():
    s = jeu()
    s["fred:T10Y2Y"] = df([("2024-06-13", 0.25, "2024-06-14")])
    v = calc(s).value
    assert v.indicateurs["pente_us_10y_2y"] == pytest.approx(0.0025)
    assert v.drapeaux["courbe_inversee_us"] is False
    assert "pente_us_10y_2y_var_3m" in v.manquants  # pas de point de comparaison : absent


def test_pente_euro_depuis_la_bce():
    s = jeu()
    s["ecb:YC_SPOT_10Y"] = df(
        [("2024-03-13", 2.8, "2024-03-14"), ("2024-06-13", 2.6, "2024-06-14")]
    )
    s["ecb:YC_SPOT_2Y"] = df([("2024-03-13", 2.9, "2024-03-14"), ("2024-06-13", 2.7, "2024-06-14")])
    v = calc(s).value
    assert v.indicateurs["pente_euro_10y_2y"] == pytest.approx((2.6 - 2.7) / 100)
    assert v.indicateurs["pente_euro_10y_2y_var_3m"] == pytest.approx(0.0)


# ------------------------------------------------------------------ données manquantes
def test_serie_absente_indicateur_absent_avec_raison_et_quadrant_none():
    s = jeu()
    del s["fred:GDPC1"]
    v = calc(s).value
    assert "croissance_pib_yoy" not in v.indicateurs
    assert "fred:GDPC1" in v.manquants["croissance_pib_yoy"]
    assert v.quadrant is None and "quadrant" in v.manquants
    assert "inflation_ipc_yoy" in v.indicateurs  # les autres indicateurs restent calculés


def test_serie_perimee_absente():
    s = jeu()
    s["fred:VIXCLS"] = df([("2024-05-01", 20.0, "2024-05-02")])  # 45 jours : plus de 10 jours
    v = calc(s).value
    assert "vix" not in v.indicateurs and "vix" in v.manquants


def test_pas_de_point_de_comparaison_a_un_an_variation_absente():
    s = jeu()
    s["fred:CPIAUCSL"] = df(
        [("2023-09-01", 290.0, "2023-10-12"), ("2024-05-01", 309.0, "2024-06-12")]
    )
    v = calc(s).value
    assert "inflation_ipc_yoy" not in v.indicateurs
    assert v.quadrant is None


def test_aucune_entree_toutes_absentes():
    v = mr.macro_regime({}, T).value
    assert v.indicateurs == {} and v.quadrant is None
    assert len(v.manquants) >= 8


def test_pente_derivee_exige_des_dates_alignees():
    s = jeu()
    s["fred:DGS2"] = df([("2024-06-12", 4.9, "2024-06-13")])  # dernière date différente de DGS10
    v = calc(s).value
    assert "pente_us_10y_2y" not in v.indicateurs and "pente_us_10y_2y" in v.manquants


def test_seuils_parametrables():
    th = mr.MacroThresholds(growth_yoy=0.04, inflation_yoy=0.01)
    assert calc(thresholds=th).value.quadrant == "stagflation"  # 3 % < 4 % ; 3 % >= 1 %
    assert calc(thresholds=th).value.seuils["growth_yoy"] == 0.04


# ------------------------------------------------------------------ non-fuite
def test_non_fuite_donnees_publiees_apres_t():
    ref = calc()
    s = jeu()
    # observations de date < t mais publiées après t, et observations datées t ou après
    s["fred:GDPC1"] = pd.concat([s["fred:GDPC1"], df([("2024-04-01", 50.0, "2024-07-25")])])
    s["fred:CPIAUCSL"] = pd.concat(
        [
            s["fred:CPIAUCSL"],
            df(
                [("2024-06-01", 999.0, "2024-07-11"), ("2024-05-01", 1.0, "2024-07-01")]
            ),  # révision future
        ]
    )
    s["fred:DGS10"] = pd.concat(
        [
            s["fred:DGS10"],
            df([("2024-06-14", 9.9, "2024-06-17"), ("2024-06-15", 9.9, "2024-06-15")]),
        ]
    )
    s["fred:VIXCLS"] = pd.concat(
        [s["fred:VIXCLS"], df([("2024-06-14", 80.0, "2024-06-15")])]
    )  # publié à t : exclu
    out = calc(s)
    assert out.value == ref.value
    assert out.meta == ref.meta


def test_une_revision_anterieure_a_t_est_prise_en_compte():
    s = jeu()
    s["fred:CPIAUCSL"] = pd.concat([s["fred:CPIAUCSL"], df([("2023-05-01", 297.0, "2024-01-10")])])
    v = calc(s).value
    assert v.indicateurs["inflation_ipc_yoy"] == pytest.approx(
        309 / 297 - 1
    )  # dernier millésime connu


def test_modifier_une_donnee_anterieure_change_la_sortie():
    ref = calc().value
    s = jeu()
    s["fred:DGS10"] = df(
        [
            ("2023-06-13", 3.7, "2023-06-14"),
            ("2024-03-13", 4.2, "2024-03-14"),
            ("2024-06-13", 4.5, "2024-06-14"),
        ]
    )
    mod = calc(s).value
    assert mod.indicateurs["taux_10y_var_3m"] != ref.indicateurs["taux_10y_var_3m"]
    assert mod.indicateurs["taux_10y_var_3m"] == pytest.approx((4.5 - 4.2) / 100)


def test_pas_de_fenetre_centree_ni_d_interpolation():
    # un point manquant à -3 mois n'est pas interpolé entre deux dates encadrantes : le point le
    # plus récent AVANT la cible est pris, ou la variation est absente
    s = jeu()
    s["fred:DGS10"] = df(
        [
            ("2023-06-13", 3.7, "2023-06-14"),
            ("2024-02-01", 3.0, "2024-02-02"),
            ("2024-06-13", 4.5, "2024-06-14"),
        ]
    )
    v = calc(s).value
    assert "taux_10y_var_3m" not in v.indicateurs  # 2024-02-01 trop ancien (> 7 j) : absent
    assert "taux_10y_var_3m" in v.manquants


def test_colonnes_manquantes_erreur_explicite():
    from amundi_agentic.tools.base import ToolError

    s = jeu()
    s["fred:VIXCLS"] = s["fred:VIXCLS"].drop(columns=["available_from"])
    v = calc(s).value  # signalé comme manquant, jamais lu sans date de publication
    assert "vix" in v.manquants and isinstance(ToolError("x"), ValueError)
