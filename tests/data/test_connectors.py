"""Connecteurs : analyse des réponses (fixtures minuscules et synthétiques), cache, reprise."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from data_helpers import ts

from amundi_agentic.data.connectors.esg import EsgConnector, sic_exclusions
from amundi_agentic.data.connectors.filings import (
    FilingsConnector,
    edgar_acceptance_to_utc,
    html_to_text,
    ny_local_to_utc,
    parse_company_facts,
    parse_company_tickers,
    parse_filings,
)
from amundi_agentic.data.connectors.fx import FxConnector
from amundi_agentic.data.connectors.macro import (
    FredConnector,
    merge_vintage_chunks,
    parse_ecb_csv,
    parse_fred_observations,
)
from amundi_agentic.data.connectors.news import NewsConnector, parse_gdelt, parse_rss
from amundi_agentic.data.connectors.prices import PricesConnector, normalize
from amundi_agentic.data.http import HttpClient
from amundi_agentic.data.models import MissingSecretError
from amundi_agentic.data.pipeline import company_query
from amundi_agentic.data.settings import load_yaml, require_secret
from amundi_agentic.data.store import ParquetStore

# --------------------------------------------------------------------------- EDGAR : fuseaux


@pytest.mark.parametrize(
    ("brut", "ny_reel"),
    [
        # (brut API, heure réelle d'acceptation à New York lue sur la page d'index)
        ("2024-02-02T04:03:38.000Z", "2024-02-01 18:03:38"),  # type AAPL : NY + 2 x décalage
        ("2025-10-31T14:01:26.000Z", "2025-10-31 06:01:26"),  # type AAPL, été
        ("2024-06-11T20:08:01.000Z", "2024-06-11 16:08:01"),  # type MSFT : vrai UTC
        ("2024-01-31T22:30:00.000Z", "2024-01-31 17:30:00"),  # vrai UTC, hiver
    ],
)
def test_acceptation_par_defaut_jamais_anterieure_a_l_instant_reel(brut, ny_reel):
    """Règle prudente (raw_as_utc) : l'instant servi n'est jamais antérieur à l'acceptation réelle."""
    reel = ny_local_to_utc(datetime.fromisoformat(ny_reel))
    assert edgar_acceptance_to_utc(brut) >= reel
    assert edgar_acceptance_to_utc(brut) == edgar_acceptance_to_utc(brut, "raw_as_utc")


def test_config_edgar_par_defaut_est_la_regle_prudente(cfg):
    assert cfg["point_in_time"]["edgar_acceptance_mode"] == "raw_as_utc"


def test_acceptation_mode_brut_toujours_posterieur_ou_egal():
    brut = "2024-02-02T04:03:38.000Z"
    assert edgar_acceptance_to_utc(brut, "raw_as_utc") == ts("2024-02-02 04:03:38")
    with pytest.raises(ValueError):
        edgar_acceptance_to_utc(brut, "corrected")  # mode supprimé
    with pytest.raises(ValueError):
        edgar_acceptance_to_utc(brut, "autre")


def test_heure_new_york_vers_utc_hiver_et_ete():
    assert ny_local_to_utc(datetime(2024, 1, 31, 17, 30)) == ts("2024-01-31 22:30")
    assert ny_local_to_utc(datetime(2024, 7, 31, 17, 30)) == ts("2024-07-31 21:30")


def test_parse_filings_ecarte_un_depot_sans_acceptation():
    rows = [
        {"accessionNumber": "1", "form": "10-K", "filingDate": "2024-02-02", "reportDate": "2023-12-31",
         "acceptanceDateTime": "2024-02-02T04:03:38.000Z", "primaryDocument": "a.htm", "items": ""},
        {"accessionNumber": "2", "form": "10-Q", "filingDate": "2024-02-03", "reportDate": "",
         "acceptanceDateTime": "", "primaryDocument": "b.htm", "items": ""},
        {"accessionNumber": "3", "form": "4", "filingDate": "2024-02-03", "reportDate": "",
         "acceptanceDateTime": "2024-02-03T04:03:38.000Z", "primaryDocument": "c.htm", "items": ""},
    ]  # fmt: skip
    df = parse_filings(rows, "AAA", 1, {"10-K", "10-Q"})
    assert df["accession"].tolist() == [
        "1"
    ]  # 2 : pas de date d'acceptation ; 3 : formulaire hors liste
    assert df["accepted_utc"].iloc[0] == ts("2024-02-02 04:03:38")  # brut lu comme UTC


def test_parse_company_tickers_et_facts():
    assert parse_company_tickers({"0": {"cik_str": 320193, "ticker": "aapl", "title": "x"}}) == {
        "AAPL": 320193
    }
    payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"start": "2023-01-01", "end": "2023-12-31", "val": 10, "accn": "a", "fy": 2023, "fp": "FY",
         "form": "10-K", "filed": "2024-02-02"},
        {"end": "2023-12-31", "val": 5, "accn": "a", "fy": 2023, "fp": "FY", "form": "10-K"},  # sans filed
    ]}}}}}  # fmt: skip
    df = parse_company_facts(payload, ["Revenues", "Absent"])
    assert len(df) == 1 and df["value"].iloc[0] == 10  # fait sans date `filed` écarté


def test_html_to_text_retire_scripts_et_entete_ixbrl():
    html = "<html><body><ix:header><div>cache</div></ix:header><script>x=1</script><p>Item&nbsp;1A</p><div>Risque</div></body></html>"
    texte = html_to_text(html)
    assert "cache" not in texte and "x=1" not in texte and "Item 1A" in texte and "Risque" in texte


# --------------------------------------------------------------------------- FRED / BCE


def test_parse_fred_garde_les_valeurs_retirees_et_les_compte():
    payload = {"observations": [
        {"realtime_start": "2024-01-01", "realtime_end": "9999-12-31", "date": "2024-01-01", "value": "1.5"},
        {"realtime_start": "2024-01-01", "realtime_end": "9999-12-31", "date": "2024-01-02", "value": "."},
    ]}  # fmt: skip
    df, manquants = parse_fred_observations(payload)
    assert manquants == 1 and len(df) == 2 and df["value"].isna().sum() == 1
    assert df["realtime_end"].iloc[0] == pd.Timestamp("2262-04-10")


def test_fusion_des_fenetres_de_millesimes():
    a = pd.DataFrame({"date": [pd.Timestamp("2024-01-01")], "realtime_start": [pd.Timestamp("2024-02-01")],
                      "realtime_end": [pd.Timestamp("2024-12-31")], "value": [1.0]})  # fmt: skip
    b = pd.DataFrame({"date": [pd.Timestamp("2024-01-01")], "realtime_start": [pd.Timestamp("2025-01-01")],
                      "realtime_end": [pd.Timestamp("2262-04-10")], "value": [1.0]})  # fmt: skip
    c = b.assign(
        realtime_start=pd.Timestamp("2025-03-01"),
        value=2.0,
        realtime_end=pd.Timestamp("2262-04-10"),
    )
    out = merge_vintage_chunks([a, b, c])
    assert out["value"].tolist() == [1.0, 2.0]  # même valeur contiguë fusionnée, révision conservée
    assert out["realtime_start"].iloc[0] == pd.Timestamp("2024-02-01")


def test_parse_ecb_csv_quotidien_et_mensuel():
    quot = "KEY,TIME_PERIOD,OBS_VALUE\nX,2024-01-02,3.9\nX,2024-01-03,\nX,2024-01-04,4.0\n"
    df = parse_ecb_csv(quot)
    assert df["value"].tolist() == [3.9, 4.0]  # observation vide écartée, non comblée
    mens = parse_ecb_csv("KEY,TIME_PERIOD,OBS_VALUE\nX,2024-01,2.5\n")
    assert mens["period_end"].iloc[0] == pd.Timestamp("2024-01-31")


class SessionJson:
    """Session factice : renvoie une charge utile selon la fin de l'URL."""

    def __init__(self, routes):
        self.routes, self.appels = routes, []

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        self.appels.append((url, dict(params or {})))
        for fin, corps in self.routes.items():
            if url.endswith(fin):
                return Resp(corps)
        raise AssertionError(f"route inconnue {url}")


class Resp:
    status_code = 200
    headers: dict = {}

    def __init__(self, corps):
        self.content = corps if isinstance(corps, bytes) else json.dumps(corps).encode()
        self.text = self.content.decode()


def _client(tmp_path, routes):
    s = SessionJson(routes)
    return HttpClient(tmp_path / "http", session=s, sleep=lambda x: None), s


def test_fred_fetch_series_cle_hors_cache_et_stockage(tmp_path, monkeypatch, cfg):
    monkeypatch.setenv("FRED_API_KEY", "CLETESTSECRETE")
    obs = {"count": 2, "limit": 100000, "observations": [
        {"realtime_start": "2024-02-01", "realtime_end": "9999-12-31", "date": "2024-01-01", "value": "1.0"},
        {"realtime_start": "2024-02-01", "realtime_end": "9999-12-31", "date": "2024-01-02", "value": "."},
    ]}  # fmt: skip
    client, sess = _client(tmp_path, {"/series/observations": obs,
                                      "/series": {"seriess": [{"title": "T", "units": "u", "frequency_short": "D"}]}})  # fmt: skip
    st = ParquetStore(tmp_path / "s")
    res = FredConnector(client, st, cfg).fetch_series("DGS10")
    assert (
        res["missing_markers"] >= 1
        and st.exists("macro/fred/DGS10")
        and st.exists("macro/fred/_meta")
    )
    assert any(p.get("api_key") == "CLETESTSECRETE" for _, p in sess.appels)  # envoyée au réseau
    for f in (tmp_path).rglob("*"):  # mais jamais écrite sur disque
        if f.is_file():
            assert b"CLETESTSECRETE" not in f.read_bytes(), f


def test_secret_manquant_ne_donne_que_le_nom(monkeypatch, tmp_path):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr("amundi_agentic.data.settings.ROOT", tmp_path)  # pas de .env
    with pytest.raises(MissingSecretError, match="FRED_API_KEY"):
        require_secret("FRED_API_KEY")


def test_fx_connecteur(tmp_path, cfg):
    csv = b"KEY,TIME_PERIOD,OBS_VALUE\nEXR,2024-01-02,1.10\nEXR,2024-01-03,1.09\n"
    client, _ = _client(tmp_path, {"D.USD.EUR.SP00.A": csv})
    st = ParquetStore(tmp_path / "s")
    FxConnector(client, st, cfg).fetch_currency("USD")
    assert st.read("fx/EXR_USD")["rate"].tolist() == [1.10, 1.09]


# --------------------------------------------------------------------------- EDGAR : connecteur


def test_edgar_user_agent_exige_et_envoye(tmp_path, cfg, monkeypatch):
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    monkeypatch.setattr("amundi_agentic.data.settings.ROOT", tmp_path)
    client, _ = _client(tmp_path, {})
    with pytest.raises(MissingSecretError, match="SEC_EDGAR_USER_AGENT"):
        FilingsConnector(client, ParquetStore(tmp_path / "s"), cfg).cik("AAA")


def test_edgar_fetch_filings_et_textes_reprise(tmp_path, cfg, monkeypatch):
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Test test@example.org")
    sub = {"name": "AAA Inc.", "sic": "3571", "sicDescription": "x", "exchanges": ["Nasdaq"],
           "filings": {"files": [], "recent": {
               "accessionNumber": ["0001-24-1"], "form": ["10-K"], "filingDate": ["2024-02-02"],
               "reportDate": ["2023-12-31"], "acceptanceDateTime": ["2024-02-02T04:03:38.000Z"],
               "primaryDocument": ["a.htm"], "items": [""]}}}  # fmt: skip
    routes = {
        "company_tickers.json": {"0": {"cik_str": 1, "ticker": "AAA", "title": "AAA"}},
        "CIK0000000001.json": sub,
        "a.htm": b"<html><body><p>Texte du rapport</p></body></html>",
    }
    client, sess = _client(tmp_path, routes)
    st = ParquetStore(tmp_path / "s")
    fc = FilingsConnector(client, st, cfg)
    assert fc.fetch_filings("AAA")["filings"] == 1
    assert fc.fetch_texts("AAA")["new_texts"] == 1
    n = len(sess.appels)
    assert fc.fetch_texts("AAA") == {"ticker": "AAA", "new_texts": 0, "already": 1}  # reprise
    assert len(sess.appels) == n
    assert "Texte du rapport" in st.read_text("filings/text/AAA/0001-24-1")
    assert st.read("filings/_companies")["sic"].iloc[0] == "3571"


# --------------------------------------------------------------------------- news

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Avec date</title><link>http://x/1</link><pubDate>Wed, 10 Jan 2024 10:00:00 GMT</pubDate></item>
<item><title>Sans date</title><link>http://x/2</link></item>
</channel></rss>"""


def test_parse_rss_ecarte_sans_date_sans_la_remplacer():
    df, stats = parse_rss(RSS, "feed", datetime(2026, 1, 1, tzinfo=UTC))
    assert stats == {"entries": 2, "no_date": 1} and len(df) == 1
    assert df["published_at"].iloc[0] == datetime(2024, 1, 10, 10, 0, tzinfo=UTC)


def test_parse_gdelt_seendate():
    payload = {
        "articles": [
            {"url": "http://a", "title": "T", "seendate": "20240110T101500Z"},
            {"url": "b"},
        ]
    }
    df, stats = parse_gdelt(payload, "AAPL", datetime(2026, 1, 1, tzinfo=UTC))
    assert stats["no_date"] == 1 and df["time_semantics"].iloc[0] == "seendate"
    assert df["published_at"].iloc[0] == datetime(2024, 1, 10, 10, 15, tzinfo=UTC)


def test_news_connecteur_dedoublonne_et_garde_first_seen(tmp_path, cfg):
    client, _ = _client(tmp_path, {"feed.xml": RSS})
    st = ParquetStore(tmp_path / "s")
    nc = NewsConnector(client, st, cfg)
    assert nc.fetch_feed("f", "http://h/feed.xml")["new"] == 1
    premier = st.read("news/items")["first_seen_at"].iloc[0]
    assert (
        nc.fetch_feed(
            "f",
            "http://h/feed.xml",
        )["new"]
        == 0
    )  # cache puis doublon
    assert (
        len(st.read("news/items")) == 1
        and st.read("news/items")["first_seen_at"].iloc[0] == premier
    )


def test_requete_gdelt_depuis_nom_de_societe():
    assert company_query("Apple Inc.") == '"Apple"'
    assert company_query("Zscaler, Inc.") == '"Zscaler"'


# --------------------------------------------------------------------------- prix


def _frame_yf(dates, closes, splits=None):
    idx = pd.DatetimeIndex(pd.to_datetime(dates)).tz_localize("America/New_York")
    n = len(dates)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": [float(c) for c in closes],
                         "Adj Close": closes, "Volume": [1.0] * n, "Dividends": [0.0] * n,
                         "Stock Splits": splits or [0.0] * n}, index=idx)  # fmt: skip


def test_normalize_ecarte_barre_du_jour_et_cloture_nulle():
    df = _frame_yf(["2024-01-02", "2024-01-03", "2024-01-04"], [1, float("nan"), 3])
    out, stats = normalize(df, date(2024, 1, 4))
    assert out["date"].tolist() == [pd.Timestamp("2024-01-02")]
    assert stats["dropped_today"] == 1 and stats["dropped_null_close"] == 1
    assert "splits" in out.columns  # « Stock Splits » renommé


def test_prix_mise_a_jour_cache_et_reprise(tmp_path, cfg):
    appels = []

    def faux(ticker, start, end):
        appels.append((ticker, start, end))
        return _frame_yf(["2024-01-02", "2024-01-03"], [10, 11]), {
            "currency": "USD",
            "exchangeName": "X",
        }

    st = ParquetStore(tmp_path / "s")
    pc = PricesConnector(
        st, cfg, tmp_path / "http", fetcher=faux, sleep=lambda x: None, today=date(2024, 1, 10)
    )
    r = pc.update("AAA")
    assert r["new_rows"] == 2 and st.read("prices/_meta")["currency"].iloc[0] == "USD"
    pc.update("AAA")  # 2e passage : l'appel réseau porte sur une fenêtre différente (mise à jour)
    assert len(appels) == 2
    pc2 = PricesConnector(
        st, cfg, tmp_path / "http", fetcher=faux, sleep=lambda x: None, today=date(2024, 1, 10)
    )
    pc2.update("AAA")
    assert len(appels) == 2  # requête identique : servie par le cache disque, pas de réseau
    assert len(st.read("prices/AAA")) == 2


def test_prix_retraitement_detecte_et_historique_recharge(tmp_path, cfg):
    etat = {"split": False}

    def faux(ticker, start, end):
        if etat["split"]:  # après un split 2:1, Yahoo divise tout l'historique par 2
            return _frame_yf(
                ["2024-01-02", "2024-01-03", "2024-01-04"], [5, 5.5, 6], [0, 0, 2.0]
            ), {}
        return _frame_yf(["2024-01-02", "2024-01-03"], [10, 11]), {}

    st = ParquetStore(tmp_path / "s")
    PricesConnector(
        st, cfg, tmp_path / "h", fetcher=faux, sleep=lambda x: None, today=date(2024, 1, 4)
    ).update("AAA")
    etat["split"] = True
    r = PricesConnector(
        st, cfg, tmp_path / "h", fetcher=faux, sleep=lambda x: None, today=date(2024, 1, 5)
    ).update("AAA")
    assert r["restated"] is True
    assert st.read("prices/AAA")["close"].tolist() == [5.0, 5.5, 6.0]


def test_prix_retry_puis_echec_signale(tmp_path, cfg):
    n = {"c": 0}

    def faux(ticker, start, end):
        n["c"] += 1
        raise RuntimeError("YFRateLimitError: Too Many Requests")

    pauses: list[float] = []
    pc = PricesConnector(
        ParquetStore(tmp_path / "s"),
        cfg,
        tmp_path / "h",
        fetcher=faux,
        sleep=pauses.append,
        today=date(2024, 1, 5),
    )
    with pytest.raises(RuntimeError):
        pc.update("AAA")
    assert n["c"] == cfg["http"]["max_attempts"] and any(
        p >= cfg["http"]["base_backoff_s"] for p in pauses
    )


# --------------------------------------------------------------------------- ESG


def test_regles_sic():
    regles = load_yaml("esg.yaml")["normative_exclusions"]
    assert sic_exclusions("2111", regles) == ["tobacco"]
    assert sic_exclusions(1221, regles) == ["thermal_coal"]
    assert "military_contracting" in sic_exclusions("3489", regles)
    assert sic_exclusions("3571", regles) == [] and sic_exclusions(None, regles) == []


def test_esg_connecteur_titres_et_etf(tmp_path):
    esg_cfg = load_yaml("esg.yaml")
    st = ParquetStore(tmp_path / "s")
    st.write(
        "filings/_companies",
        pd.DataFrame({"ticker": ["AAA", "BBB", "CCC"], "sic": ["2111", "3571", None]}),
    )
    vendeur = {"AAA": {"totalEsg": 30.5, "tobacco": True}, "BBB": None}

    def faux(t):
        if t == "CCC":
            raise RuntimeError("503")
        return vendeur[t]

    c = EsgConnector(st, esg_cfg, vendor=faux, now=lambda: datetime(2026, 10, 2, tzinfo=UTC))
    a, b, cc = c.update_stock("AAA"), c.update_stock("BBB"), c.update_stock("CCC")
    assert a["score"] == 30.5 and a["exclusions"] == "tobacco" and a["determined"]
    assert b["score"] is None and b["determined"] and b["exclusions"] == ""
    assert not cc["determined"] and "no_sic" in cc["notes"] and "vendor_error" in cc["notes"]
    pab = c.update_etf("CRP.PA")
    assert pab["determined"] and "tobacco" in pab["exclusions"]
    inconnu = c.update_etf("XXX")
    assert not inconnu["determined"] and inconnu["exclusion_basis"] is None
    assert len(st.read("esg/records")) == 5


# --------------------------------------------------------------------------- FRED : règle de délai


class SessionAvecErreurs:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        for fin, (statut, corps) in self.routes.items():
            if url.endswith(fin):
                r = Resp(corps)
                r.status_code = statut
                return r
        raise AssertionError(url)


def test_fred_serie_de_marche_disponibilite_par_regle_de_delai(tmp_path, monkeypatch, cfg):
    monkeypatch.setenv("FRED_API_KEY", "CLETEST")
    obs = {"count": 2, "limit": 100000, "observations": [
        {"realtime_start": "2026-10-01", "realtime_end": "9999-12-31", "date": "2024-01-02", "value": "4.0"},
        {"realtime_start": "2026-10-01", "realtime_end": "9999-12-31", "date": "2024-01-03", "value": "."},
    ]}  # fmt: skip
    client, _ = _client(
        tmp_path, {"/series/observations": obs, "/series": {"seriess": [{"title": "T"}]}}
    )
    st = ParquetStore(tmp_path / "s")
    FredConnector(client, st, cfg).fetch_series("DGS10")  # revised: false dans la config
    df = st.read("macro/fred/DGS10")
    assert (df["availability"] == "lag_rule").all()
    assert df["realtime_start"].iloc[0] == pd.Timestamp("2024-01-03")  # date + 1 jour
    from amundi_agentic.data.pit import PointInTimeStore

    pit = PointInTimeStore(st, cfg)
    assert pit.as_of(date(2024, 1, 3)).macro(["fred:DGS10"]).empty  # publiée le 3 : pas avant t
    assert len(pit.as_of(date(2024, 1, 4)).macro(["fred:DGS10"])) == 1


def test_fred_serie_inexistante_signalee_indisponible(tmp_path, monkeypatch, cfg):
    monkeypatch.setenv("FRED_API_KEY", "CLETEST")
    s = SessionAvecErreurs(
        {"/series": (400, {"error_message": "Bad Request.  The series does not exist."})}
    )
    client = HttpClient(tmp_path / "h", session=s, sleep=lambda x: None)
    st = ParquetStore(tmp_path / "s")
    res = FredConnector(client, st, cfg).fetch_series("BAMLEC0A0RMEY")
    assert res["unavailable"] is True and not st.exists("macro/fred/BAMLEC0A0RMEY")
    assert st.last_events()[("fred", "BAMLEC0A0RMEY")]["status"] == "unavailable"


def test_reindexation_sans_reseau_selon_le_mode(tmp_path):
    from amundi_agentic.data.connectors.filings import reindex_acceptance

    st = ParquetStore(tmp_path / "s")
    st.write(
        "filings/index/AAA",
        pd.DataFrame({"acceptance_raw": ["2024-02-02T04:03:38.000Z"], "accepted_utc": [pd.NaT]}),
    )
    assert reindex_acceptance(st, "raw_as_utc") == 1
    assert st.read("filings/index/AAA")["accepted_utc"].iloc[0] == ts("2024-02-02 04:03:38")


def test_lag_rule_fred_un_jour_ouvre_vendredi_donne_lundi(tmp_path, monkeypatch, cfg):
    monkeypatch.setenv("FRED_API_KEY", "CLETEST")
    obs = {"count": 1, "limit": 100000, "observations": [
        {"realtime_start": "2026-10-01", "realtime_end": "9999-12-31", "date": "2024-01-05", "value": "4.0"},
    ]}  # fmt: skip
    client, _ = _client(
        tmp_path, {"/series/observations": obs, "/series": {"seriess": [{"title": "T"}]}}
    )
    st = ParquetStore(tmp_path / "s")
    FredConnector(client, st, cfg).fetch_series("DGS10")  # vendredi 5 janvier 2024
    assert st.read("macro/fred/DGS10")["realtime_start"].iloc[0] == pd.Timestamp("2024-01-08")
    from amundi_agentic.data.pit import PointInTimeStore

    pit = PointInTimeStore(st, cfg)
    assert pit.as_of(date(2024, 1, 8)).macro(["fred:DGS10"]).empty  # lundi : publiée le jour même
    assert len(pit.as_of(date(2024, 1, 9)).macro(["fred:DGS10"])) == 1


def test_lag_rule_saute_les_jours_feries_americains():
    from amundi_agentic.data.connectors.macro import us_business_days

    # vendredi 24 mai 2024, lundi 27 = Memorial Day : disponible le mardi 28, servi à t = 29
    assert pd.Timestamp("2024-05-24") + us_business_days(1) == pd.Timestamp("2024-05-28")
    assert pd.Timestamp("2024-05-03") + us_business_days(1) == pd.Timestamp("2024-05-06")


def test_config_refuse_un_mode_d_acceptation_autre(monkeypatch):
    from amundi_agentic.data import settings

    cfg = settings.load_yaml("data.yaml")
    cfg["point_in_time"]["edgar_acceptance_mode"] = "corrected"
    monkeypatch.setattr(settings, "load_yaml", lambda n: cfg)
    with pytest.raises(ValueError):
        settings.DataSettings.load()
