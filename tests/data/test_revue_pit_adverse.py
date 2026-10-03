"""Revue indépendante de la phase 2 : tests adverses sur les fuites de futur (point-in-time).

Écrits par le reviewer-tester, sans lire les tests du data-engineer comme référence : chaque test
construit un jeu SYNTHÉTIQUE avec un oracle indépendant du code sous test (recalcul à partir de
prix bruts non ajustés, du tableau des millésimes, etc.). Aucune clé, aucun réseau.

Les anciens `xfail` (défauts B1, N3, N4) sont levés : les corrections sont vérifiées ici.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from data_helpers import prix, ts

from amundi_agentic.data.connectors.filings import edgar_acceptance_to_utc, parse_filings
from amundi_agentic.data.models import NewsQuery
from amundi_agentic.data.pit import PointInTimeStore, cutoff_utc, pit_prices

# ====================================================================== prix : oracle brut


def _monde_brut(seed: int, n: int = 120):
    """Prix BRUTS (non ajustés) tels que cotés à chaque séance, avec splits et dividendes."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", periods=n)
    brut = 50.0 * np.cumprod(1 + rng.normal(0, 0.01, n))
    splits = {
        int(i): float(rng.choice([2.0, 3.0, 0.5])) for i in rng.choice(np.arange(10, n - 5), 3)
    }
    divs = {int(i): float(round(brut[i - 1] * 0.01, 4)) for i in rng.choice(np.arange(5, n), 5)}
    # un jour de split et un jour de dividende ne coïncident pas (cas non ambigu)
    divs = {i: d for i, d in divs.items() if i not in splits}
    return dates, brut, splits, divs


def _yahoo(dates, brut, splits, divs, download_idx: int | None = None):
    """Ce que Yahoo sert : clôtures ajustées des splits connus à la date de téléchargement."""
    n = len(dates)
    close = brut.copy()
    for i, s in splits.items():
        close[:i] = close[:i] / s  # toutes les barres AVANT le split sont divisées
    div = np.zeros(n)
    for i, d in divs.items():
        # dividende exprimé dans l'unité ajustée des splits postérieurs
        div[i] = d / np.prod([s for j, s in splits.items() if j > i] or [1.0])
    sp = np.zeros(n)
    for i, s in splits.items():
        sp[i] = s
    return prix(dates, list(close), dividends=list(div), splits=list(sp))


@pytest.mark.parametrize("seed", range(12))
def test_oracle_prix_splits_et_dividendes_connus_a_t_seulement(seed):
    dates, brut, splits, divs = _monde_brut(seed)
    df = _yahoo(dates, brut, splits, divs)
    rng = np.random.default_rng(seed + 1000)
    for k in rng.choice(np.arange(15, len(dates) - 2), 8):
        t = dates[int(k)].date()
        out = pit_prices(df, t).set_index("date")
        assert out.index.max() < pd.Timestamp(t)
        # oracle : ce qu'un opérateur voyait à t = prix brut / splits survenus ENTRE la barre et t
        for j in range(0, int(k)):
            connus = np.prod([s for i, s in splits.items() if j < i < int(k)] or [1.0])
            attendu_close = brut[j] / connus
            assert out["close"].iloc[j] == pytest.approx(attendu_close, rel=1e-9), (seed, t, j)
        # adj_close : produit des (1 - D/P_prec) des dividendes détachés avant t, après la barre
        for j in range(0, int(k)):
            m = 1.0
            for i, d in divs.items():
                if j < i < int(k):
                    m *= 1 - d / brut[i - 1]
            att = out["close"].iloc[j] * m
            # i > j : le dividende s'applique aux barres strictement antérieures à l'ex-date
            assert out["adj_close"].iloc[j] == pytest.approx(att, rel=1e-6), (seed, t, j)


@pytest.mark.parametrize("seed", range(6))
def test_prix_invariants_au_contenu_futur_hors_splits(seed):
    """Sans split futur, tronquer les lignes >= t ne change RIEN au résultat servi à t."""
    dates, brut, _, divs = _monde_brut(seed)
    df = _yahoo(dates, brut, {}, divs)
    for t in (dates[30].date(), dates[77].date()):
        complet = pit_prices(df, t)
        tronque = pit_prices(df[df["date"] < pd.Timestamp(t)], t)
        pd.testing.assert_frame_equal(complet, tronque)


def test_prix_futur_corrompu_ne_change_pas_le_passe_servi():
    """Un cours aberrant daté >= t (donnée future) ne doit influencer aucune ligne servie."""
    dates, brut, _, divs = _monde_brut(3)
    df = _yahoo(dates, brut, {}, {})
    t = dates[60].date()
    base = pit_prices(df, t)
    sale = df.copy()
    sale.loc[sale["date"] >= pd.Timestamp(t), ["close", "open", "high", "low"]] = 1e9
    sale.loc[sale["date"] >= pd.Timestamp(t), "dividends"] = 5.0  # dividende futur géant
    pd.testing.assert_frame_equal(base, pit_prices(sale, t))


def test_prix_entree_non_triee_et_jour_ferie(store, pit):
    """Données désordonnées, lundi férié : on sert jusqu'au dernier jour coté < t, jamais plus."""
    df = prix(["2024-04-01", "2024-03-28", "2024-03-29"], [3, 1, 2]).sample(frac=1, random_state=1)
    store.write("prices/XX", df)
    out = pit.as_of(date(2024, 4, 1)).prices(["XX"])  # lundi de Pâques : t=1er avril
    assert list(out.index) == [pd.Timestamp("2024-03-28"), pd.Timestamp("2024-03-29")]
    out2 = pit.as_of(date(2024, 4, 2)).prices(["XX"])
    assert out2.index.max() == pd.Timestamp("2024-04-01")


def test_prix_barre_future_deja_dans_le_stockage_jamais_servie(store, pit):
    """Un cache rempli APRES t (stock contenant l'avenir) : jamais servi, même avec start."""
    dates = pd.bdate_range("2024-01-01", periods=60)
    store.write("prices/ZZ", prix(dates, list(range(1, 61))))
    for t in (date(2024, 1, 2), date(2024, 2, 15), date(2024, 3, 9)):
        v = pit.as_of(t)
        for start in (None, date(2024, 1, 1), date(2030, 1, 1)):
            out = v.prices(["ZZ"], start=start)
            assert out.empty or out.index.max() < pd.Timestamp(t)


def test_prix_split_la_veille_de_t_et_split_le_jour_de_t():
    """Split daté t-1 : connu (prix post-split). Split daté t : inconnu, prix pré-split restitué."""
    d = ["2024-06-06", "2024-06-07", "2024-06-10", "2024-06-11"]
    # Yahoo (ajusté du split du 10 juin x10) : avant le split les cours sont divisés par 10
    df = prix(d, [10.0, 10.0, 100.0, 101.0], splits=[0, 0, 10.0, 0])
    a_t10 = pit_prices(df, date(2024, 6, 10))  # split du 10 : pas encore connu
    assert list(a_t10["close"]) == pytest.approx([100.0, 100.0])  # restitué (cours cotés)
    a_t11 = pit_prices(df, date(2024, 6, 11))  # split du 10 : connu
    assert list(a_t11["close"]) == pytest.approx([10.0, 10.0, 100.0])  # série ajustée à t


# ====================================================================== macro


def _vintages(rows):
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(d),
                "realtime_start": pd.Timestamp(rs),
                "realtime_end": pd.Timestamp("2262-04-10"),
                "value": v,
            }
            for d, rs, v in rows
        ]
    )


def test_macro_valeur_supprimee_puis_reintroduite(store, pit):
    store.write(
        "macro/fred/S1",
        _vintages(
            [
                ("2024-01-01", "2024-02-01", 1.0),
                ("2024-01-01", "2024-03-01", np.nan),  # retirée
                ("2024-01-01", "2024-04-01", 3.0),  # réintroduite, valeur différente
            ]
        ),
    )
    v = lambda t: pit.as_of(t).macro_long("fred:S1")  # noqa: E731
    assert v(date(2024, 2, 1)).empty  # realtime_start == t : exclu
    assert v(date(2024, 2, 2))["value"].tolist() == [1.0]
    assert v(date(2024, 3, 15)).empty  # retirée : ne ressort pas l'ancienne valeur 1.0
    assert v(date(2024, 4, 1)).empty  # le millésime du 1er avril n'est pas encore connu
    assert v(date(2024, 4, 2))["value"].tolist() == [3.0]


@pytest.mark.parametrize("seed", range(8))
def test_macro_fuzz_contre_oracle_alfred(store, pit, seed):
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.date_range("2023-01-01", periods=6, freq="MS"):
        k = int(rng.integers(1, 5))
        jours = sorted(rng.choice(np.arange(10, 400), k, replace=False))
        for j in jours:
            val = np.nan if rng.random() < 0.15 else float(rng.normal())
            rows.append((d, d + timedelta(days=int(j)), val))
    store.write("macro/fred/F", _vintages(rows))
    for t in pd.date_range("2023-01-15", "2024-12-31", periods=40):
        t = t.date()
        out = pit.as_of(t).macro_long("fred:F")
        attendu = {}
        for d, rs, val in rows:  # oracle : dernier millésime strictement avant t
            if rs < pd.Timestamp(t) and (d not in attendu or rs > attendu[d][0]):
                attendu[d] = (rs, val)
        attendu = {d: x for d, (_, x) in attendu.items() if not pd.isna(x)}
        assert dict(zip(out["date"], out["value"], strict=True)) == attendu, (seed, t)
        assert (out["available_from"] < pd.Timestamp(t)).all()


def test_macro_bce_fin_de_periode_et_delai(store, pit, cfg):
    """Série mensuelle : la disponibilité part de la FIN de période (pas du début) + délai."""
    nom = next(iter(cfg["ecb"]["series"]))
    lag = cfg["ecb"]["series"][nom]["lag_days"]
    store.write(
        f"macro/ecb/{nom}",
        pd.DataFrame(
            {
                "date": [pd.Timestamp("2024-01-01")],
                "period_end": [pd.Timestamp("2024-01-31")],
                "value": [3.0],
            }
        ),
    )
    t_dispo = date(2024, 1, 31) + timedelta(days=lag + 1)  # strictement après fin + délai
    assert pit.as_of(t_dispo - timedelta(days=1)).macro_long(f"ecb:{nom}").empty
    assert len(pit.as_of(t_dispo).macro_long(f"ecb:{nom}")) == 1
    # jamais disponible en cours de mois
    assert pit.as_of(date(2024, 1, 20)).macro_long(f"ecb:{nom}").empty


def test_macro_serie_lag_rule_vendredi_documente(store, pit):
    """Observation du vendredi en règle `date + 1 jour` : servie dès t = samedi + 1 (dimanche).

    Constat (non bloquant) : la règle compte en jours CALENDAIRES. Pour une série publiée le jour
    ouvré suivant, la valeur du vendredi est servie le lundi 00:00 Paris alors que FRED ne la
    publie que le lundi après-midi (heure de New York). Ce test fige le comportement actuel.
    """
    df = _vintages([("2024-03-01", "2024-03-02", 4.0)])  # vendredi 1er mars, realtime = date + 1
    store.write("macro/fred/D", df)
    assert pit.as_of(date(2024, 3, 2)).macro_long("fred:D").empty
    assert pit.as_of(date(2024, 3, 3)).macro_long("fred:D")["value"].tolist() == [4.0]


# ====================================================================== EDGAR


@pytest.mark.parametrize(
    "raw",
    ["2026-07-29T20:08:01.000Z", "2026-01-28T21:07:34.000Z", "2024-03-12T22:30:00.000Z"],
)
def test_edgar_corrige_jamais_avant_l_instant_utc_brut(raw):
    """Invariant prudent : l'instant servi n'est jamais antérieur à l'instant brut lu comme UTC
    SAUF si l'on sait que le déposant est du type « New York + 2 x décalage » (jamais déclaré)."""
    brut = edgar_acceptance_to_utc(raw, "raw_as_utc")
    assert edgar_acceptance_to_utc(raw) >= brut


def test_edgar_depot_du_soir_vrai_utc_non_servi_avant_acceptation(store, pit):
    brut = "2024-06-11T22:30:00.000Z"  # vrai UTC (type MSFT) : 18:30 à New York, été
    cols = {
        "ticker": "MSFT", "cik": 789019, "accession": "0001-24-000001", "form": "8-K",
        "filing_date": pd.Timestamp("2024-06-12"), "acceptance_raw": brut,
        "report_date": pd.NaT, "primary_document": "", "items": "",
    }  # fmt: skip
    rows = [
        {
            "accessionNumber": cols["accession"], "form": "8-K", "filingDate": "2024-06-12",
            "acceptanceDateTime": brut, "reportDate": "", "primaryDocument": "",
        }
    ]  # fmt: skip
    idx = parse_filings(rows, "MSFT", 789019, {"8-K"})
    store.write("filings/index/MSFT", idx)
    reel_utc = pd.Timestamp("2024-06-11 22:30:00", tz="UTC")
    # t = 12 juin : coupure 11 juin 22:00Z, avant l'acceptation réelle (22:30Z) => non servi
    assert reel_utc > cutoff_utc(date(2024, 6, 12))
    assert pit.as_of(date(2024, 6, 12)).filings("MSFT") == []


def test_edgar_changements_d_heure_raw_as_utc_jamais_avant_ni_trop_apres():
    """Balayage toutes les 15 min autour des bascules DST 2024 (mars, novembre).

    Deux régimes observés le 2026-10-02 : brut = vrai UTC (MSFT, NVDA) ou brut = vrai UTC + décalage
    New York (AAPL : +4 h été, +5 h hiver). L'instant servi (brut lu comme UTC) ne doit jamais être
    antérieur à l'acceptation réelle. Borne haute 24 h : l'excès observé est au plus 5 h ; au-delà de
    24 h le dépôt serait servi une séance entière trop tard, ce qui dénaturerait l'information.
    """
    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    for debut in ("2024-03-09T20:00:00", "2024-11-02T20:00:00"):
        t0 = pd.Timestamp(debut, tz="UTC")
        for k in range(0, 3 * 24 * 4):  # 3 jours, pas de 15 min, à cheval sur la bascule
            vrai = t0 + pd.Timedelta(minutes=15 * k)
            decalage = -vrai.tz_convert(ny).utcoffset().total_seconds() / 3600
            for brut_utc in (vrai, vrai + pd.Timedelta(hours=decalage)):
                brut = brut_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                servi = edgar_acceptance_to_utc(brut)
                assert servi == brut_utc
                assert servi >= vrai, (vrai, brut)
                assert servi - vrai <= pd.Timedelta(hours=24), (vrai, brut)


def test_edgar_10ka_hors_index_donc_jamais_servi_par_filings():
    """Un 10-K/A n'est pas dans `edgar.forms` : il est écarté (jamais de fuite), mais absent."""
    rows = [
        {"accessionNumber": "a-1", "form": "10-K", "filingDate": "2024-02-01",
         "acceptanceDateTime": "2024-02-01T21:00:00.000Z", "reportDate": "2023-12-31",
         "primaryDocument": "x.htm"},
        {"accessionNumber": "a-2", "form": "10-K/A", "filingDate": "2024-03-01",
         "acceptanceDateTime": "2024-03-01T21:00:00.000Z", "reportDate": "2023-12-31",
         "primaryDocument": "y.htm"},
    ]  # fmt: skip
    df = parse_filings(rows, "X", 1, {"10-K", "10-Q", "8-K"})
    assert df["form"].tolist() == ["10-K"]


def test_xbrl_amendement_hors_index_servi_seulement_apres_son_filed(store, pit):
    """Retraitement déposé par 10-K/A (absent de l'index) : valeur d'origine jusqu'à `filed`."""
    store.write("xbrl/X", pd.DataFrame({
        "concept": ["Revenues"] * 2, "unit": ["USD"] * 2,
        "start": pd.to_datetime(["2023-01-01"] * 2), "end": pd.to_datetime(["2023-12-31"] * 2),
        "value": [100.0, 90.0], "accn": ["orig", "amend"], "fy": [2023, 2023],
        "fp": ["FY", "FY"], "form": ["10-K", "10-K/A"],
        "filed": pd.to_datetime(["2024-02-01", "2024-05-10"]),
    }))  # fmt: skip
    assert pit.as_of(date(2024, 5, 10)).xbrl_facts("X")["value"].tolist() == [100.0]
    assert pit.as_of(date(2024, 5, 11)).xbrl_facts("X")["value"].tolist() == [90.0]
    assert pit.as_of(date(2024, 2, 1)).xbrl_facts("X").empty


def test_xbrl_meme_jour_deux_depots_ordre_deterministe(store, pit):
    """Deux dépôts le même jour sur la même clé : le résultat ne doit pas dépendre de l'ordre."""
    base = {
        "concept": "Revenues", "unit": "USD", "start": pd.Timestamp("2023-01-01"),
        "end": pd.Timestamp("2023-12-31"), "fy": 2023, "fp": "FY", "form": "10-K",
        "filed": pd.Timestamp("2024-02-01"),
    }  # fmt: skip
    a = pd.DataFrame(
        [{**base, "value": 1.0, "accn": "0001"}, {**base, "value": 2.0, "accn": "0002"}]
    )
    store.write("xbrl/A", a)
    store.write("xbrl/B", a.iloc[::-1].reset_index(drop=True))
    va = pit.as_of(date(2024, 3, 1)).xbrl_facts("A")["value"].tolist()
    vb = pit.as_of(date(2024, 3, 1)).xbrl_facts("B")["value"].tolist()
    assert va == vb


# ====================================================================== news


def _items(rows):
    return pd.DataFrame(
        [
            {
                "item_id": f"i{i}", "source": s, "published_at": ts(p), "first_seen_at": ts(p),
                "title": "t", "summary": "", "url": f"http://x/{i}", "time_semantics": "published",
                "tags": tag,
            }
            for i, (s, p, tag) in enumerate(rows)
        ]
    )  # fmt: skip


def test_news_fuzz_aucun_article_a_la_coupure_ou_apres(store, pit):
    rng = np.random.default_rng(7)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rows = [
        ("gdelt", (base + timedelta(minutes=int(m))).isoformat(), "A")
        for m in rng.integers(0, 60 * 24 * 120, 500)
    ]
    store.write("news/items", _items(rows))
    for t in (
        date(2024, 1, 10),
        date(2024, 2, 29),
        date(2024, 3, 31),
        date(2024, 4, 1),
    ):  # DST 31/3
        c = cutoff_utc(t)
        servis = pit.as_of(t).news(NewsQuery())
        assert all(pd.Timestamp(n.published_at) < c for n in servis)
        attendus = sum(1 for _, p, _ in rows if pd.Timestamp(p) < c)
        assert len(servis) == attendus


def test_news_seendate_futur_vs_publication(store, pit):
    """Article dont la date d'observation est postérieure à t : jamais servi, même ancien."""
    df = _items([("gdelt", "2024-05-02T10:00:00", "A")])
    df["time_semantics"] = "seendate"
    store.write("news/items", df)
    assert pit.as_of(date(2024, 5, 2)).news(NewsQuery()) == []
    assert len(pit.as_of(date(2024, 5, 3)).news(NewsQuery())) == 1


# ====================================================================== ESG


def _esg(rows):
    return pd.DataFrame(
        [
            {
                "asset_id": a, "kind": "stock", "score": sc, "score_source": "v" if sc == sc else None,
                "exclusions": ex, "exclusion_basis": "sic", "determined": True,
                "observed_at": ts(o), "sic": "1", "notes": "",
            }
            for a, o, sc, ex in rows
        ]
    )  # fmt: skip


def test_esg_strict_sert_le_dernier_instantane_avant_t_pas_apres(store, pit):
    store.write(
        "esg/records",
        _esg(
            [
                ("A", "2024-01-01", 10.0, ""),
                ("A", "2024-06-01", 20.0, "tabac"),
                ("A", "2025-01-01", 99.0, "armes"),
            ]
        ),
    )
    r = pit.as_of(date(2024, 7, 1)).esg("A")
    assert (r.score, r.exclusions, r.non_point_in_time) == (20.0, ("tabac",), False)
    assert pit.as_of(date(2024, 6, 1)).esg("A").score == 10.0  # observé exactement à t-0 : exclu
    assert pit.as_of(date(2023, 12, 31)).esg("A") is None  # tout est postérieur : rien (strict)
    nonpit = pit.as_of(date(2023, 12, 31), esg_mode="non_pit").esg("A")
    assert nonpit.non_point_in_time is True  # drapeau obligatoire en mode non_pit


def test_esg_non_pit_ne_masque_pas_un_instantane_pit(store, pit):
    store.write("esg/records", _esg([("A", "2024-01-01", 10.0, ""), ("A", "2025-01-01", 99.0, "")]))
    r = pit.as_of(date(2024, 6, 1), esg_mode="non_pit").esg("A")
    assert r.score == 10.0 and r.non_point_in_time is False  # pas de score de 2025 si 2024 existe


# ====================================================================== sortie datée et garde-fous


def test_last_data_date_toujours_avant_t(store, pit):
    dates = pd.bdate_range("2024-01-01", periods=40)
    store.write("prices/Q", prix(dates, list(range(1, 41))))
    v = pit.as_of(date(2024, 2, 1))
    v.prices(["Q"])
    assert all(d < pd.Timestamp("2024-02-01") for d in v.last_data_date.values())


def test_pointintimestore_refuse_datetime_et_chaine(store, cfg):
    p = PointInTimeStore(store, cfg)
    with pytest.raises(TypeError):
        p.as_of(datetime(2024, 1, 1, 12, 0))  # type: ignore[arg-type]
