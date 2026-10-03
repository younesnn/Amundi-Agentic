"""Contre-vérification indépendante des corrections de la revue phase 2 (B1, N1, N2, N5, N7, N10)."""

from __future__ import annotations

import ast
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from data_helpers import prix

from amundi_agentic.data.connectors.filings import edgar_acceptance_to_utc, parse_filings
from amundi_agentic.data.connectors.macro import FredConnector
from amundi_agentic.data.pit import cutoff_utc
from amundi_agentic.data.quality import check_prices
from amundi_agentic.data.settings import DataSettings

ROOT = Path(__file__).resolve().parents[2]

# (déposant, brut API, instant réel UTC lu sur la page d'index NY du dépôt)
CAS_EDGAR = [
    ("MSFT été (vrai UTC)", "2026-07-29T20:08:01.000Z", "2026-07-29 20:08:01"),
    ("MSFT hiver (vrai UTC)", "2026-01-28T21:07:34.000Z", "2026-01-28 21:07:34"),
    ("AAPL été (brut +4 h)", "2026-07-31T14:01:02.000Z", "2026-07-31 10:01:02"),
    ("AAPL hiver (brut +5 h)", "2026-02-25T02:55:58.000Z", "2026-02-24 21:55:58"),
    ("avant bascule DST 2024 (vrai UTC)", "2024-03-08T22:30:00.000Z", "2024-03-08 22:30:00"),
    ("après bascule DST 2024 (vrai UTC)", "2024-03-12T22:30:00.000Z", "2024-03-12 22:30:00"),
    ("avant bascule DST 2024 (brut +5 h)", "2024-03-09T03:30:00.000Z", "2024-03-08 22:30:00"),
    ("après bascule DST 2024 (brut +4 h)", "2024-03-13T02:30:00.000Z", "2024-03-12 22:30:00"),
    ("bascule d'automne (brut +4 h)", "2024-11-01T02:30:00.000Z", "2024-10-31 22:30:00"),
    ("après bascule d'automne (vrai UTC)", "2024-11-05T22:30:00.000Z", "2024-11-05 22:30:00"),
]


@pytest.mark.parametrize(("nom", "brut", "reel"), CAS_EDGAR)
def test_b1_defaut_jamais_avant_acceptation_reelle(nom, brut, reel, store, pit):
    reel_utc = pd.Timestamp(reel, tz="UTC")
    assert edgar_acceptance_to_utc(brut) >= reel_utc, nom
    rows = [{"accessionNumber": "a-1", "form": "8-K", "filingDate": brut[:10],
             "acceptanceDateTime": brut, "reportDate": "", "primaryDocument": ""}]  # fmt: skip
    store.write("filings/index/X", parse_filings(rows, "X", 1, {"8-K"}))
    for k in range(-3, 4):  # toute date t : servi seulement si l'acceptation réelle < coupure
        t = (reel_utc + pd.Timedelta(days=k)).date()
        if pit.as_of(t).filings("X"):
            assert reel_utc < cutoff_utc(t), (nom, t)


def test_b1_config_par_defaut_et_mode_corrected_supprime(tmp_path, monkeypatch):
    from amundi_agentic.data import settings as st_mod

    assert DataSettings.load().config["point_in_time"]["edgar_acceptance_mode"] == "raw_as_utc"
    brut = "2026-07-29T20:08:01.000Z"
    assert edgar_acceptance_to_utc(brut) == pd.Timestamp(brut)  # défaut : brut lu comme UTC
    for mode in ("corrected", "", "RAW_AS_UTC", "ny"):  # tout autre mode est refusé
        with pytest.raises(ValueError):
            edgar_acceptance_to_utc(brut, mode)
        with pytest.raises(ValueError):
            parse_filings(
                [{"accessionNumber": "a", "form": "8-K", "filingDate": "2026-07-29",
                  "acceptanceDateTime": brut}], "X", 1, {"8-K"}, mode,
            )  # fmt: skip
    # une configuration modifiée à la main est refusée au chargement
    conf = tmp_path / "config"
    conf.mkdir()
    texte = (ROOT / "config" / "data.yaml").read_text(encoding="utf-8")
    assert "edgar_acceptance_mode: raw_as_utc" in texte
    (conf / "data.yaml").write_text(
        texte.replace("edgar_acceptance_mode: raw_as_utc", "edgar_acceptance_mode: corrected"),
        encoding="utf-8",
    )
    monkeypatch.setattr(st_mod, "CONFIG_DIR", conf)
    with pytest.raises(ValueError):
        DataSettings.load(tmp_path)


# ---------------------------------------------------------------- N1 : règle en jours ouvrés
def test_n1_vendredi_non_servi_le_lundi_servi_le_mardi(store, pit):
    d = pd.Timestamp("2024-03-01")  # vendredi
    store.write(
        "macro/fred/V",
        pd.DataFrame({"date": [d], "realtime_start": [d + pd.offsets.BDay(1)],
                      "realtime_end": [pd.Timestamp("2262-04-10")], "value": [4.0]}),
    )  # fmt: skip
    assert pit.as_of(date(2024, 3, 4)).macro_long("fred:V").empty  # lundi : non servi
    assert pit.as_of(date(2024, 3, 5)).macro_long("fred:V")["value"].tolist() == [4.0]


def test_n1_fetch_series_calcule_la_disponibilite_en_jours_ouvres(tmp_path, monkeypatch, cfg):
    """Branche réelle de `fetch_series` (non révisée) : realtime_start = date + 1 jour ouvré."""
    from amundi_agentic.data.store import ParquetStore

    st = ParquetStore(tmp_path / "s")
    fc = FredConnector(client=None, store=st, cfg={"fred": {"series": {"S": {"revised": False}}}})
    obs = pd.DataFrame({"date": pd.to_datetime(["2024-03-01", "2024-03-04"]), "value": [1.0, 2.0],
                        "realtime_start": pd.NaT, "realtime_end": pd.NaT})  # fmt: skip
    monkeypatch.setattr(fc, "_get", lambda *a, **k: {"seriess": [{}]})
    monkeypatch.setattr(fc, "_latest", lambda sid: (obs.copy(), 0))
    fc.fetch_series("S")
    out = st.read("macro/fred/S").sort_values("date")
    assert out["realtime_start"].tolist() == pd.to_datetime(["2024-03-04", "2024-03-05"]).tolist()
    assert (out["availability"] == "lag_rule").all()


# Fériés fédéraux américains 2024 codés EN DUR (indépendants du code du projet)
FERIES_US_2024 = {
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 5, 27), date(2024, 6, 19),
    date(2024, 7, 4), date(2024, 9, 2), date(2024, 10, 14), date(2024, 11, 11),
    date(2024, 11, 28), date(2024, 12, 25),
}  # fmt: skip


def _jour_ouvre_suivant(d: date) -> date:
    """Premier jour ouvré américain STRICTEMENT après d (week-end et fériés exclus)."""
    from datetime import timedelta

    n = d + timedelta(days=1)
    while n.weekday() >= 5 or n in FERIES_US_2024:
        n += timedelta(days=1)
    return n


@pytest.mark.parametrize(
    ("obs", "dispo"),
    [
        (date(2024, 5, 24), date(2024, 5, 28)),  # vendredi avant Memorial Day (lundi 27) -> mardi
        (date(2024, 7, 3), date(2024, 7, 5)),  # mercredi, jeudi 4 juillet férié -> vendredi
        (date(2024, 11, 27), date(2024, 11, 29)),  # veille de Thanksgiving -> vendredi
        (date(2024, 12, 24), date(2024, 12, 26)),  # veille de Noël -> jeudi
        (date(2024, 3, 1), date(2024, 3, 4)),  # vendredi ordinaire -> lundi
        (date(2024, 3, 5), date(2024, 3, 6)),  # mardi ordinaire -> mercredi
    ],
)
def test_n1_jours_feries_via_fetch_series_puis_as_of(tmp_path, monkeypatch, obs, dispo):
    """Chemin réel : `fetch_series` (réponse simulée) puis `as_of`, attendu issu du calendrier du test."""
    from amundi_agentic.data.pit import PointInTimeStore
    from amundi_agentic.data.store import ParquetStore

    assert _jour_ouvre_suivant(obs) == dispo  # contrôle du calendrier du test lui-même
    cfg = {"fred": {"series": {"S": {"revised": False}}}}
    st = ParquetStore(tmp_path / "s")
    fc = FredConnector(client=None, store=st, cfg=cfg)
    brut = pd.DataFrame({"date": [pd.Timestamp(obs)], "value": [1.0],
                         "realtime_start": pd.NaT, "realtime_end": pd.NaT})  # fmt: skip
    monkeypatch.setattr(fc, "_get", lambda *a, **k: {"seriess": [{}]})
    monkeypatch.setattr(fc, "_latest", lambda sid: (brut.copy(), 0))
    fc.fetch_series("S")
    assert st.read("macro/fred/S")["realtime_start"].iloc[0] == pd.Timestamp(dispo)
    from datetime import timedelta

    pit = PointInTimeStore(st, {})
    assert pit.as_of(dispo).macro_long("fred:S").empty  # t = jour de disponibilité : exclu
    assert pit.as_of(dispo + timedelta(days=1)).macro_long("fred:S")["value"].tolist() == [1.0]


# ---------------------------------------------------------------- N2 : rapport sans écriture racine
def test_n2_write_report_out_n_ecrit_pas_a_la_racine(tmp_path):
    from amundi_agentic.data.coverage import write_report

    avant = {
        p: p.read_bytes() if p.exists() else None
        for p in (ROOT / "runs/data_coverage/couverture.json", ROOT / "docs/couverture_donnees.md")
    }
    out = tmp_path / "rapport" / "c.md"
    write_report(DataSettings.load(tmp_path), out=out)
    assert out.is_file() and out.with_suffix(".json").is_file()
    for p, contenu in avant.items():
        assert (p.read_bytes() if p.exists() else None) == contenu, p


# ---------------------------------------------------------------- N5 : saut avec et sans volume
def _serie_saut(volume_saut: float):
    dates = pd.bdate_range("2024-01-01", periods=60)
    close = [100.0] * 30 + [50.0] * 30
    close = list(np.array(close) + np.arange(60) * 0.01)
    df = prix(dates, close)
    df["volume"] = 1000.0
    df.loc[30, "volume"] = volume_saut
    return df


def test_n5_saut_avec_pic_de_volume_est_un_avertissement_reel():
    q = DataSettings.load().config["quality"]
    iss = [i for i in check_prices(_serie_saut(10_000.0), "T", q) if i.kind == "split"]
    assert len(iss) == 1 and iss[0].severity == "warning" and "probablement réel" in iss[0].detail


def test_n5_saut_sans_volume_signale_un_split_possible():
    q = DataSettings.load().config["quality"]
    iss = [i for i in check_prices(_serie_saut(1000.0), "T", q) if i.kind == "split"]
    assert len(iss) == 1 and "split non ajusté possible" in iss[0].detail
    assert iss[0].severity in ("warning", "error")  # jamais silencieux


# ---------------------------------------------------------------- N7 : départage chronologique
def test_n7_depots_du_meme_jour_departages_par_acceptation_pas_par_accn(store, pit):
    base = {"concept": "Revenues", "unit": "USD", "start": pd.Timestamp("2023-01-01"),
            "end": pd.Timestamp("2023-12-31"), "fy": 2023, "fp": "FY", "form": "10-K",
            "filed": pd.Timestamp("2024-02-01")}  # fmt: skip
    # accn alphabétiquement inversé par rapport au temps : « zzz » accepté AVANT « aaa »
    store.write("xbrl/T", pd.DataFrame([{**base, "value": 1.0, "accn": "zzz"},
                                        {**base, "value": 2.0, "accn": "aaa"}]))  # fmt: skip
    rows = [
        {"accessionNumber": a, "form": "10-K", "filingDate": "2024-02-01",
         "acceptanceDateTime": h, "reportDate": "", "primaryDocument": ""}
        for a, h in (("zzz", "2024-02-01T14:00:00.000Z"), ("aaa", "2024-02-01T20:00:00.000Z"))
    ]  # fmt: skip
    store.write("filings/index/T", parse_filings(rows, "T", 1, {"10-K"}))
    assert pit.as_of(date(2024, 3, 1)).xbrl_facts("T")["value"].tolist() == [2.0]  # le plus tardif


# ---------------------------------------------------------------- N10 : pas de fuite de modules
def test_n10_aucun_import_helpers_de_premier_niveau():
    for f in (ROOT / "tests").rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ImportFrom) and n.module == "helpers":
                pytest.fail(f"{f} importe `helpers` (nom générique)")
            if isinstance(n, ast.Import) and any(a.name == "helpers" for a in n.names):
                pytest.fail(f"{f} importe `helpers`")


def test_n10_modules_exposes_par_pythonpath_sont_nommes_sans_collision():
    """Tout .py de tests/data visible en premier niveau doit avoir un nom spécifique au projet."""
    generiques = {"helpers", "utils", "common", "fixtures", "base", "tools", "mocks"}
    noms = {p.stem for p in (ROOT / "tests" / "data").glob("*.py")}
    assert not (noms & generiques), noms & generiques
    autres = {p.stem for d in (ROOT / "tests").iterdir() if d.is_dir() and d.name != "data"
              for p in d.rglob("*.py")}  # fmt: skip
    assert not ((noms - {"conftest"}) & autres), noms & autres


def test_n10_pythonpath_ne_masque_aucun_module_du_projet():
    r = subprocess.run([sys.executable, "-c", "import sys;sys.path.insert(0,'tests/data');"
                        "import amundi_agentic.data, data_helpers;print('ok')"],
                       cwd=ROOT, capture_output=True, text=True)  # fmt: skip
    assert r.stdout.strip() == "ok", r.stderr


# ---------------------------------------------------------------- add_us_business_days vs calendrier du test
def _feries_federaux(annee: int) -> set[date]:
    """Fériés fédéraux américains calculés par règles (indépendant de pandas), avec report
    d'observance : samedi -> vendredi, dimanche -> lundi."""
    from datetime import timedelta

    def nieme(mois, jour_sem, n):  # n-ième jour de semaine du mois (n=-1 : dernier)
        if n > 0:
            d = date(annee, mois, 1)
            d += timedelta(days=(jour_sem - d.weekday()) % 7 + 7 * (n - 1))
            return d
        d = date(annee, mois + 1, 1) - timedelta(days=1) if mois < 12 else date(annee, 12, 31)
        return d - timedelta(days=(d.weekday() - jour_sem) % 7)

    fixes = [date(annee, 1, 1), date(annee, 7, 4), date(annee, 11, 11), date(annee, 12, 25)]
    if annee >= 2021:
        fixes.append(date(annee, 6, 19))  # Juneteenth, fête fédérale depuis 2021
    obs = set()
    for d in fixes:
        obs.add(
            d - timedelta(days=1)
            if d.weekday() == 5
            else d + timedelta(days=1)
            if d.weekday() == 6
            else d
        )
    obs |= {nieme(1, 0, 3), nieme(2, 0, 3), nieme(5, 0, -1), nieme(9, 0, 1),
            nieme(10, 0, 2), nieme(11, 3, 4)}  # fmt: skip
    return obs


def test_feries_du_test_sur_des_dates_connues():
    f = _feries_federaux(2024) | _feries_federaux(2025) | _feries_federaux(2023)
    assert {date(2024, 5, 27), date(2024, 6, 19), date(2024, 10, 14), date(2024, 11, 11),
            date(2024, 11, 28), date(2024, 12, 25), date(2024, 7, 4), date(2024, 9, 2),
            date(2024, 1, 15), date(2024, 2, 19), date(2024, 1, 1)} <= f  # fmt: skip
    assert date(2023, 12, 25) in f and date(2023, 6, 19) in f
    assert date(2021, 12, 31) in _feries_federaux(2022)  # 1er janvier 2022 = samedi
    assert date(2022, 6, 20) in _feries_federaux(2022)  # Juneteenth dimanche -> lundi
    assert date(2020, 6, 19) not in _feries_federaux(2020)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_add_us_business_days_egal_calendrier_du_test_2020_2026(n):
    from datetime import timedelta

    from amundi_agentic.data.connectors.macro import add_us_business_days

    feries = set()
    for a in range(2019, 2028):
        feries |= _feries_federaux(a)
    jours = pd.date_range("2020-01-01", "2026-12-31")  # tous les jours, week-ends compris

    def suivant(d: date) -> date:
        compte = 0
        while compte < n:
            d += timedelta(days=1)
            if d.weekday() < 5 and d not in feries:
                compte += 1
        return d

    attendu = [pd.Timestamp(suivant(d.date())) for d in jours]
    out = add_us_business_days(pd.Series(jours), n)
    ecarts = [
        (a.date(), b.date(), c.date())
        for a, b, c in zip(jours, out, attendu, strict=True)
        if b != c
    ]
    assert not ecarts, ecarts[:5]
    assert add_us_business_days(pd.Series([], dtype="datetime64[ns]"), n).empty
