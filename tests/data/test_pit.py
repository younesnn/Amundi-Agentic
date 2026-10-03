"""Accès point-in-time as_of(t) : aucune donnée publiée à la coupure de t ou après n'est servie.

Critère d'acceptation de la phase 2 (EX-NF-11, EX-O1-16, L1 §11.3, D-023). Coupure : t 00:00 Paris.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest
from data_helpers import prix, ts

from amundi_agentic.data.models import LookAheadError, NewsQuery
from amundi_agentic.data.pit import cutoff_utc, pit_prices

# --------------------------------------------------------------------------- coupure


def test_coupure_hiver_et_ete():
    assert cutoff_utc(date(2024, 2, 1)) == ts("2024-01-31 23:00")  # UTC+1
    assert cutoff_utc(date(2024, 7, 1)) == ts("2024-06-30 22:00")  # UTC+2


def test_as_of_refuse_un_datetime(pit):
    with pytest.raises(TypeError):
        pit.as_of(datetime(2024, 2, 1, 12, 0))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- prix


def _store_prix(store):
    dates = pd.bdate_range("2024-01-02", "2024-02-29")
    store.write("prices/AAA", prix(dates, list(range(100, 100 + len(dates)))))


def test_prix_aucune_barre_a_t_ou_apres(store, pit):
    _store_prix(store)
    for t in pd.date_range("2024-01-03", "2024-03-05"):
        p = pit.as_of(t.date()).prices(["AAA"])
        assert (p.index < t).all(), t


def test_prix_bord_barre_de_t_exclue_et_t_moins_1_incluse(store, pit):
    _store_prix(store)
    p = pit.as_of(date(2024, 1, 10)).prices(["AAA"])
    assert p.index.max() == pd.Timestamp("2024-01-09")  # clôture de t-1 : incluse
    assert pd.Timestamp("2024-01-10") not in p.index  # barre de t : exclue


def test_prix_lundi_sert_le_vendredi(store, pit):
    _store_prix(store)
    p = pit.as_of(date(2024, 1, 8)).prices(["AAA"])  # lundi
    assert p.index.max() == pd.Timestamp("2024-01-05")  # vendredi


def test_prix_start_et_trou_non_comble(store, pit):
    dates = ["2024-01-02", "2024-01-03", "2024-01-09"]  # trou du 4 au 8
    store.write("prices/AAA", prix(dates, [1, 2, 3]))
    store.write("prices/BBB", prix(["2024-01-03", "2024-01-09"], [5, 6]))
    p = pit.as_of(date(2024, 1, 20)).prices(["AAA", "BBB"], start=date(2024, 1, 3))
    assert list(p.index) == list(pd.to_datetime(["2024-01-03", "2024-01-09"]))
    assert len(p) == 2  # aucune date intermédiaire inventée
    full = pit.as_of(date(2024, 1, 20)).prices(["AAA", "BBB"])
    assert full["BBB"].isna().iloc[0]  # NaN signalé, pas interpolé


def test_prix_ticker_inconnu_leve_une_erreur(pit):
    with pytest.raises(KeyError):
        pit.as_of(date(2024, 1, 10)).prices(["ZZZ"])


def test_split_futur_non_applique_a_t(store, pit):
    # Yahoo : avant le split 2:1 du 2024-01-08, les clôtures sont déjà divisées par 2 (valeurs 50).
    dates = ["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    store.write("prices/SPL", prix(dates, [50, 51, 52, 53], splits=[0, 0, 2.0, 0]))
    avant = pit.as_of(date(2024, 1, 8)).prices(["SPL"], field="close")  # split pas encore connu
    assert avant["SPL"].tolist() == [100.0, 102.0]  # niveaux tels qu'observés à l'époque
    apres = pit.as_of(date(2024, 1, 10)).prices(["SPL"], field="close")  # split connu
    assert apres["SPL"].tolist() == [50.0, 51.0, 52.0, 53.0]


def test_dividende_futur_non_integre_au_prix_ajuste(store, pit):
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    # dividende de 10 détaché le 2024-01-04 (clôture veille : 100)
    store.write("prices/DIV", prix(dates, [100, 100, 90, 90], dividends=[0, 0, 10.0, 0]))
    a_t3 = pit.as_of(date(2024, 1, 4)).prices(["DIV"])  # ex-date = t : inconnu
    assert a_t3["DIV"].tolist() == [100.0, 100.0]
    a_t6 = pit.as_of(date(2024, 1, 6)).prices(["DIV"])
    assert a_t6["DIV"].round(6).tolist() == [90.0, 90.0, 90.0, 90.0]  # 100*(1-10/100)


def test_pit_prices_rendement_de_jonction_non_fausse_par_un_split_futur():
    """Sans le recalage, le rendement du 03/01 au 04/01 passerait de +9 % à -45 % (split 2:1)."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    brut = prix(dates, [50, 55, 60], splits=[0, 0, 2.0])  # split le 04/01 déjà dans les cours Yahoo
    vu_le_03 = pit_prices(brut, date(2024, 1, 4))["close"]
    assert vu_le_03.tolist() == [100.0, 110.0]
    assert vu_le_03.pct_change().iloc[-1] == pytest.approx(0.10)


# --------------------------------------------------------------------------- macro FRED (ALFRED)


def _fred(store, lignes, nom="GDPC1"):
    df = pd.DataFrame(lignes, columns=["date", "realtime_start", "realtime_end", "value"]).astype(
        {"value": float}
    )
    for c in ("date", "realtime_start", "realtime_end"):
        df[c] = pd.to_datetime(df[c])
    store.write(f"macro/fred/{nom}", df)


def test_macro_revision_posterieure_a_t_ignoree(store, pit):
    _fred(
        store,
        [
            ("2024-01-01", "2024-04-25", "2024-05-29", 100.0),  # première estimation
            ("2024-01-01", "2024-05-30", "2262-04-10", 105.0),  # révision publiée le 30 mai
        ],
    )
    avant = pit.as_of(date(2024, 5, 1)).macro(["fred:GDPC1"])
    assert avant["fred:GDPC1"].tolist() == [100.0]
    apres = pit.as_of(date(2024, 6, 15)).macro(["fred:GDPC1"])
    assert apres["fred:GDPC1"].tolist() == [105.0]


def test_macro_bords_realtime_start_egal_t_exclu(store, pit):
    _fred(store, [("2024-01-01", "2024-04-25", "2262-04-10", 100.0)])
    assert pit.as_of(date(2024, 4, 25)).macro(["fred:GDPC1"]).empty  # publié le jour de t : exclu
    assert len(pit.as_of(date(2024, 4, 26)).macro(["fred:GDPC1"])) == 1  # publié la veille : servi


def test_macro_observation_pas_encore_publiee_absente(store, pit):
    _fred(
        store,
        [
            ("2024-01-01", "2024-04-25", "2262-04-10", 1.0),
            ("2024-04-01", "2024-07-25", "2262-04-10", 2.0),
        ],
    )
    m = pit.as_of(date(2024, 6, 1)).macro_long("fred:GDPC1")
    assert m["date"].tolist() == [pd.Timestamp("2024-01-01")]


def test_macro_valeur_retiree_par_un_millesime_ne_reapparait_pas(store, pit):
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "realtime_start": pd.to_datetime(["2024-02-01", "2024-03-01"]),
            "realtime_end": pd.to_datetime(["2024-02-29", "2262-04-10"]),
            "value": [1.0, float("nan")],  # le millésime de mars retire la valeur
        }
    )
    store.write("macro/fred/X", df)
    assert pit.as_of(date(2024, 2, 15)).macro(["fred:X"])["fred:X"].tolist() == [1.0]
    assert pit.as_of(date(2024, 4, 1)).macro(["fred:X"]).empty


def test_macro_bce_delai_de_publication(store, pit, cfg):
    store.write(
        "macro/ecb/ESTR",
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-02"]),
                "period_end": pd.to_datetime(["2024-01-02"]),
                "value": [3.9],
            }
        ),
    )
    lag = cfg["ecb"]["series"]["ESTR"]["lag_days"]
    assert lag == 1
    assert (
        pit.as_of(date(2024, 1, 3)).macro(["ecb:ESTR"]).empty
    )  # publié le 3 au matin : pas avant t
    assert len(pit.as_of(date(2024, 1, 4)).macro(["ecb:ESTR"])) == 1


# --------------------------------------------------------------------------- dépôts SEC


def _index(store, ticker, lignes):
    df = pd.DataFrame(
        lignes,
        columns=["accession", "form", "filing_date", "accepted_utc", "primary_document"],
    )
    df["ticker"], df["cik"], df["report_date"] = ticker, 1, pd.NaT
    df["acceptance_raw"], df["items"] = "", ""
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["accepted_utc"] = pd.to_datetime(df["accepted_utc"], utc=True)
    store.write(f"filings/index/{ticker}", df)


def test_fuseau_edgar_converti(store, pit):
    """Accepté 17:30 à New York le 31/01 = 22:30 UTC : avant la coupure du 01/02 (23:00 UTC)."""
    _index(
        store,
        "AAA",
        [
            ("a-1", "10-K", "2024-01-31", "2024-01-31 22:30:00", "x.htm"),  # 17:30 NY : servi
            ("a-2", "10-Q", "2024-02-01", "2024-01-31 23:30:00", "y.htm"),  # 18:30 NY : pas servi
        ],
    )
    vue = pit.as_of(date(2024, 2, 1))
    assert [f.accession for f in vue.filings("AAA")] == ["a-1"]
    assert [f.accession for f in pit.as_of(date(2024, 2, 2)).filings("AAA")] == ["a-1", "a-2"]


def test_depot_accepte_exactement_a_la_coupure_exclu(store, pit):
    _index(store, "AAA", [("a-1", "8-K", "2024-01-31", "2024-01-31 23:00:00", "x.htm")])
    assert pit.as_of(date(2024, 2, 1)).filings("AAA") == []
    _index(store, "AAA", [("a-1", "8-K", "2024-01-31", "2024-01-31 22:59:59", "x.htm")])
    assert len(pit.as_of(date(2024, 2, 1)).filings("AAA")) == 1


def test_depot_ete_coupure_22h_utc(store, pit):
    _index(store, "AAA", [("a-1", "8-K", "2024-06-28", "2024-06-30 22:00:00", "x.htm")])
    assert pit.as_of(date(2024, 7, 1)).filings("AAA") == []  # coupure = 30/06 22:00 UTC (été)


def test_texte_de_depot_posterieur_leve_lookahead(store, pit):
    _index(store, "AAA", [("a-1", "10-K", "2024-03-01", "2024-03-01 12:00:00", "x.htm")])
    store.write_text("filings/text/AAA/a-1", "contenu")
    with pytest.raises(LookAheadError):
        pit.as_of(date(2024, 2, 1)).filing_text("AAA", "a-1")
    assert pit.as_of(date(2024, 3, 2)).filing_text("AAA", "a-1") == "contenu"


def test_filtre_par_formulaire(store, pit):
    _index(
        store,
        "AAA",
        [
            ("a-1", "10-K", "2024-01-10", "2024-01-10 12:00:00", "x.htm"),
            ("a-2", "8-K", "2024-01-11", "2024-01-11 12:00:00", "y.htm"),
        ],
    )
    out = pit.as_of(date(2024, 2, 1)).filings("AAA", {"10-K"})
    assert [f.form for f in out] == ["10-K"]


# --------------------------------------------------------------------------- XBRL


def _xbrl(store, lignes, index=None):
    df = pd.DataFrame(lignes, columns=["concept", "unit", "start", "end", "value", "accn", "filed"])
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c])
    df["fy"], df["fp"], df["form"] = 2023, "FY", "10-K"
    store.write("xbrl/AAA", df)
    if index:
        _index(store, "AAA", index)


def test_xbrl_retraitement_posterieur_ignore(store, pit):
    _xbrl(
        store,
        [
            ("Revenues", "USD", "2023-01-01", "2023-12-31", 100.0, "a-1", "2024-02-10"),
            ("Revenues", "USD", "2023-01-01", "2023-12-31", 90.0, "a-2", "2025-02-10"),  # retraité
        ],
    )
    f = pit.as_of(date(2024, 6, 1)).xbrl_facts("AAA")
    assert f["value"].tolist() == [100.0]
    f2 = pit.as_of(date(2025, 6, 1)).xbrl_facts("AAA")
    assert f2["value"].tolist() == [90.0]  # le dernier dépôt filed < t l'emporte


def test_xbrl_filed_egal_t_exclu(store, pit):
    _xbrl(store, [("Revenues", "USD", "2023-01-01", "2023-12-31", 1.0, "a-1", "2024-02-10")])
    assert pit.as_of(date(2024, 2, 10)).xbrl_facts("AAA").empty
    assert len(pit.as_of(date(2024, 2, 11)).xbrl_facts("AAA")) == 1


def test_xbrl_ceinture_acceptation_connue_apres_coupure(store, pit):
    # filed (date) < t mais acceptation connue de l'index après la coupure : exclu
    _xbrl(
        store,
        [("Revenues", "USD", "2023-01-01", "2023-12-31", 1.0, "a-1", "2024-01-31")],
        index=[("a-1", "10-K", "2024-01-31", "2024-01-31 23:30:00", "x.htm")],
    )
    assert pit.as_of(date(2024, 2, 1)).xbrl_facts("AAA").empty


def test_xbrl_filtre_concepts(store, pit):
    _xbrl(
        store,
        [
            ("Revenues", "USD", "2023-01-01", "2023-12-31", 1.0, "a-1", "2024-01-10"),
            ("Assets", "USD", None, "2023-12-31", 2.0, "a-1", "2024-01-10"),
        ],
    )
    out = pit.as_of(date(2024, 3, 1)).xbrl_facts("AAA", ["Assets"])
    assert out["concept"].tolist() == ["Assets"]


# --------------------------------------------------------------------------- news


def _news(store, lignes):
    df = pd.DataFrame(
        lignes, columns=["item_id", "source", "published_at", "title", "summary", "tags"]
    )
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    df["first_seen_at"] = df["published_at"]
    df["url"], df["time_semantics"] = "u", "published"
    store.write("news/items", df)


def test_news_publiee_exactement_a_la_coupure_exclue(store, pit):
    _news(
        store,
        [
            ("1", "rss", "2024-01-31 22:59:59", "avant", "", ""),
            ("2", "rss", "2024-01-31 23:00:00", "pile", "", ""),
            ("3", "rss", "2024-01-31 23:00:01", "apres", "", ""),
        ],
    )
    titres = [n.title for n in pit.as_of(date(2024, 2, 1)).news(NewsQuery())]
    assert titres == ["avant"]


def test_news_fuseau_paris_minuit_local(store, pit):
    # 2024-02-01 00:30 à Paris = 2024-01-31 23:30 UTC : postérieur à la coupure du 1er février
    _news(store, [("1", "rss", "2024-01-31 23:30:00", "x", "", "")])
    assert pit.as_of(date(2024, 2, 1)).news(NewsQuery()) == []
    assert len(pit.as_of(date(2024, 2, 2)).news(NewsQuery())) == 1


def test_news_filtres_termes_tags_limite_tri(store, pit):
    _news(
        store,
        [
            ("1", "rss", "2024-01-10 10:00:00", "Apple annonce", "", "AAPL"),
            ("2", "gdelt", "2024-01-11 10:00:00", "Autre", "résumé apple", "AAPL"),
            ("3", "rss", "2024-01-12 10:00:00", "Banque centrale", "", ""),
        ],
    )
    vue = pit.as_of(date(2024, 2, 1))
    assert [n.item_id for n in vue.news(NewsQuery(terms=("APPLE",)))] == ["2", "1"]
    assert [n.item_id for n in vue.news(NewsQuery(tags=("AAPL",), limit=1))] == ["2"]
    assert [n.item_id for n in vue.news(NewsQuery(sources=("rss",)))] == ["3", "1"]


def test_news_sans_donnees(pit):
    assert pit.as_of(date(2024, 2, 1)).news(NewsQuery()) == []


# --------------------------------------------------------------------------- ESG


def _esg(store, observe):
    store.write(
        "esg/records",
        pd.DataFrame(
            {
                "asset_id": ["AAA"],
                "kind": ["stock"],
                "score": [20.0],
                "score_source": ["vendor"],
                "exclusions": ["tobacco"],
                "exclusion_basis": ["sic"],
                "determined": [True],
                "observed_at": [pd.Timestamp(observe, tz="UTC")],
                "sic": ["2111"],
                "notes": [""],
            }
        ),
    )


def test_esg_instantane_posterieur_a_t_non_servi_en_strict(store, pit):
    _esg(store, "2026-10-02")
    assert pit.as_of(date(2024, 2, 1)).esg("AAA") is None


def test_esg_non_pit_servi_avec_drapeau(store, pit):
    _esg(store, "2026-10-02")
    rec = pit.as_of(date(2024, 2, 1), esg_mode="non_pit").esg("AAA")
    assert rec is not None and rec.non_point_in_time is True and rec.exclusions == ("tobacco",)


def test_esg_instantane_anterieur_servi_comme_pit(store, pit):
    _esg(store, "2024-01-15")
    rec = pit.as_of(date(2024, 2, 1)).esg("AAA")
    assert rec is not None and rec.non_point_in_time is False


def test_esg_mode_invalide(pit):
    with pytest.raises(ValueError):
        pit.as_of(date(2024, 2, 1), esg_mode="autre")


# --------------------------------------------------------------------------- change


def test_change_fixing_de_t_exclu(store, pit):
    store.write(
        "fx/EXR_USD",
        pd.DataFrame({"date": pd.to_datetime(["2024-01-09", "2024-01-10"]), "rate": [1.09, 1.10]}),
    )
    s = pit.as_of(date(2024, 1, 10)).fx_eur("USD")
    assert s.index.max() == pd.Timestamp("2024-01-09")


# --------------------------------------------------------------------------- balayage global


def test_aucune_donnee_posterieure_a_t(store, pit):
    """Pour de nombreuses dates t, aucune source ne sert une donnée datée à la coupure ou après."""
    _store_prix(store)
    _fred(
        store,
        [
            ("2024-01-01", "2024-02-10", "2024-03-09", 1.0),
            ("2024-01-01", "2024-03-10", "2262-04-10", 2.0),
            ("2024-04-01", "2024-05-10", "2262-04-10", 3.0),
        ],
    )
    _index(
        store,
        "AAA",
        [
            ("a-1", "10-K", "2024-02-10", "2024-02-10 21:00:00", "x"),
            ("a-2", "10-Q", "2024-05-10", "2024-05-10 21:00:00", "x"),
        ],
    )
    _xbrl(
        store,
        [
            ("Revenues", "USD", "2023-01-01", "2023-12-31", 1.0, "a-1", "2024-02-10"),
            ("Revenues", "USD", "2024-01-01", "2024-03-31", 2.0, "a-2", "2024-05-10"),
        ],
    )
    _news(
        store,
        [
            (str(i), "rss", f"2024-0{1 + i % 5}-1{i % 9} 12:00:00", f"t{i}", "", "")
            for i in range(30)
        ],
    )
    _esg(store, "2024-03-01")
    store.write(
        "fx/EXR_USD",
        pd.DataFrame({"date": pd.bdate_range("2024-01-02", "2024-06-28"), "rate": 1.1}),
    )
    for t in pd.date_range("2024-01-02", "2024-06-30", freq="3D"):
        vue = pit.as_of(t.date())
        cut = vue.cutoff
        assert (vue.prices(["AAA"]).index < pd.Timestamp(t.date())).all()
        ml = vue.macro_long("fred:GDPC1")
        assert (ml["available_from"] < pd.Timestamp(t.date())).all()
        assert all(f.accepted_utc < cut for f in vue.filings("AAA"))
        assert (vue.xbrl_facts("AAA")["filed"] < pd.Timestamp(t.date())).all()
        assert all(n.published_at < cut for n in vue.news(NewsQuery()))
        e = vue.esg("AAA")
        assert e is None or e.observed_at < cut
        assert (vue.fx_eur("USD").index < pd.Timestamp(t.date())).all()
        for cle, dernier in vue.last_data_date.items():  # sorties datées par la dernière donnée
            dernier = dernier.tz_convert("UTC") if dernier.tzinfo else dernier.tz_localize("UTC")
            assert dernier < cut + pd.Timedelta(days=0), cle


def test_xbrl_deux_depots_le_meme_jour_departages_par_l_acceptation(store, pit):
    # accn "z" accepté avant "a" : l'ordre alphabétique donnerait la mauvaise valeur
    _xbrl(
        store,
        [
            ("Revenues", "USD", "2023-01-01", "2023-12-31", 1.0, "z-1", "2024-02-10"),
            ("Revenues", "USD", "2023-01-01", "2023-12-31", 2.0, "a-1", "2024-02-10"),
        ],
        index=[
            ("z-1", "10-K", "2024-02-10", "2024-02-10 09:00:00", "x"),
            ("a-1", "10-K/A", "2024-02-10", "2024-02-10 15:00:00", "x"),
        ],
    )
    assert pit.as_of(date(2024, 3, 1)).xbrl_facts("AAA")["value"].tolist() == [2.0]
