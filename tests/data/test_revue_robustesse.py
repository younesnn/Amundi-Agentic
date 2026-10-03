"""Revue indépendante de la phase 2 : robustesse réseau, secrets, atomicité, idempotence.

Sans réseau ni clé réelle : les secrets de test sont des valeurs factices.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd
import pytest
import requests

from amundi_agentic.data.connectors.news import NewsConnector
from amundi_agentic.data.connectors.prices import PricesConnector
from amundi_agentic.data.http import HttpClient, HttpError, redact
from amundi_agentic.data.store import ParquetStore

SRC = Path(__file__).resolve().parents[2] / "src" / "amundi_agentic"


class R:
    def __init__(self, status=200, content=b"{}", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}
        self.text = content.decode()


class Sess:
    def __init__(self, reps):
        self.reps, self.n = list(reps), 0

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        self.n += 1
        r = self.reps.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def cl(tmp_path, reps, **kw):
    pauses: list[float] = []
    s = Sess(reps)
    return (
        HttpClient(tmp_path / "h", session=s, sleep=pauses.append, jitter=lambda: 0.0,
                   clock=lambda: 0.0, **kw),
        s,
        pauses,
    )  # fmt: skip


# ---------------------------------------------------------------------- secrets
def test_exception_reseau_avec_cle_dans_l_url_est_expurgee(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "FAUXSECRET0123456789")
    msg = "HTTPSConnectionPool: Max retries exceeded with url: /f?series_id=X&api_key=FAUXSECRET0123456789&file_type=json"
    c, _, _ = cl(tmp_path, [requests.ConnectionError(msg)] * 2, max_attempts=2)
    with pytest.raises(HttpError) as e:
        c.get(
            "fred", "https://x.org/f", params={"api_key": "FAUXSECRET0123456789", "series_id": "X"}
        )
    assert "FAUXSECRET0123456789" not in str(e.value) and "FAUXSECRET0123456789" not in repr(
        e.value
    )
    assert "FAUXSECRET0123456789" not in e.value.body


def test_corps_d_erreur_http_expurge(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "FAUXSECRET0123456789")
    body = b'{"error":"bad api_key=FAUXSECRET0123456789 for request"}'
    c, _, _ = cl(tmp_path, [R(400, body)])
    with pytest.raises(HttpError) as e:
        c.get("fred", "https://x.org/f")
    assert "FAUXSECRET0123456789" not in e.value.body and "FAUXSECRET0123456789" not in str(e.value)


def test_redact_motifs_courants():
    assert "SECRETVALUE" not in redact("GET /x?apikey=SECRETVALUE&a=1")
    assert "SECRETVALUE" not in redact('{"url": "https://h/p?token=SECRETVALUE"}')


def test_cle_hors_url_dans_les_journaux_d_evenements(tmp_path):
    st = ParquetStore(tmp_path / "s")
    st.log_event("fred", "X", "error", redact("boom api_key=ABCDEFSECRET"))
    assert "ABCDEFSECRET" not in (tmp_path / "s" / "_status" / "events.jsonl").read_text()


# ---------------------------------------------------------------------- erreurs réseau
@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_codes_transitoires_rejoues_puis_succes(tmp_path, code):
    c, s, pauses = cl(tmp_path, [R(code), R(code), R(200, b"ok")])
    assert c.get("x", "https://x.org/a").content == b"ok" and s.n == 3 and len(pauses) == 2


def test_retry_after_au_format_date_ne_plante_pas(tmp_path):
    c, _, _ = cl(
        tmp_path, [R(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), R(200)]
    )
    assert c.get("x", "https://x.org/a").status == 200


def test_retry_after_enorme_est_plafonne(tmp_path):
    c, _, pauses = cl(
        tmp_path, [R(429, headers={"Retry-After": "999999"}), R(200)], max_backoff_s=60
    )
    c.get("x", "https://x.org/a")
    assert max(pauses) <= 60


def test_404_non_rejoue_et_timeout_epuise_les_essais(tmp_path):
    c, s, _ = cl(tmp_path, [R(404)])
    with pytest.raises(HttpError) as e:
        c.get("x", "https://x.org/a")
    assert e.value.status == 404 and s.n == 1
    c2, s2, _ = cl(tmp_path / "b", [requests.Timeout("t")] * 3, max_attempts=3)
    with pytest.raises(HttpError):
        c2.get("x", "https://x.org/b")
    assert s2.n == 3


def test_echec_n_ecrit_rien_dans_le_cache(tmp_path):
    c, _, _ = cl(tmp_path, [R(503)] * 2, max_attempts=2)
    with pytest.raises(HttpError):
        c.get("x", "https://x.org/a")
    assert not list((tmp_path / "h").rglob("*.bin"))


def test_ttl_expire_force_un_nouvel_appel(tmp_path):
    c, s, _ = cl(tmp_path, [R(200, b"1"), R(200, b"2")])
    c.get("x", "https://x.org/a", ttl_s=3600)
    meta = next((tmp_path / "h").rglob("*.json"))
    info = json.loads(meta.read_text())
    info["fetched_at"] = "2000-01-01T00:00:00+00:00"
    meta.write_text(json.dumps(info))
    assert c.get("x", "https://x.org/a", ttl_s=3600).content == b"2" and s.n == 2


def test_reponse_200_non_json_gdelt_ne_doit_pas_etre_cachee_a_vie(tmp_path):
    cfg = {"news": {"gdelt": {"max_records": 5, "backfill_max_records": 5, "probe_months_back": [],
                              "probe_query": "x"}}}  # fmt: skip
    c, s, _ = cl(tmp_path, [R(200, b"Timeout. Please try again."), R(200, b'{"articles": []}')])
    nc = NewsConnector(c, ParquetStore(tmp_path / "s"), cfg)
    with pytest.raises(HttpError):
        nc.backfill_week('"Apple"', "AAPL", 3)
    # relance : la requête doit repartir sur le réseau, pas relire le texte d'erreur en cache
    assert nc.backfill_week('"Apple"', "AAPL", 3)["entries"] == 0


def test_article_gdelt_commun_a_deux_actifs_garde_les_deux_etiquettes(tmp_path):
    cfg = {"news": {"gdelt": {"max_records": 5}}}
    payload = json.dumps(
        {
            "articles": [
                {"url": "http://a/1", "title": "Apple et Microsoft", "seendate": "20240110T101500Z"}
            ]
        }
    ).encode()
    c, _, _ = cl(tmp_path, [R(200, payload), R(200, payload)])
    st = ParquetStore(tmp_path / "s")
    nc = NewsConnector(c, st, cfg)
    nc.fetch_gdelt('"Apple"', "AAPL")
    nc.fetch_gdelt('"Microsoft"', "MSFT")
    tags = set(str(st.read("news/items")["tags"].iloc[0]).split("|"))
    assert tags == {"AAPL", "MSFT"}


# ---------------------------------------------------------------------- stockage
def test_ecriture_atomique_un_echec_laisse_l_ancien_fichier(tmp_path, monkeypatch):
    st = ParquetStore(tmp_path / "s")
    st.write("d/x", pd.DataFrame({"a": [1, 2, 3]}))

    def boom(self, *a, **k):
        raise OSError("disque plein")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)
    with pytest.raises(OSError):
        st.write("d/x", pd.DataFrame({"a": [9]}))
    monkeypatch.undo()
    assert st.read("d/x")["a"].tolist() == [1, 2, 3]
    assert st.datasets("d") == ["d/x"]  # aucun fichier temporaire pris pour un jeu de données


def test_remplacement_interrompu_ne_corrompt_pas(tmp_path, monkeypatch):
    st = ParquetStore(tmp_path / "s")
    st.write("d/x", pd.DataFrame({"a": [1]}))
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("kill")))
    with pytest.raises(OSError):
        st.write("d/x", pd.DataFrame({"a": [2]}))
    monkeypatch.undo()
    assert st.read("d/x")["a"].tolist() == [1]
    assert st.datasets("d") == ["d/x"]


def test_upsert_idempotent_et_derniere_ligne_gagne(tmp_path):
    st = ParquetStore(tmp_path / "s")
    a = pd.DataFrame({"k": [1, 2], "v": [10, 20]})
    assert st.upsert("d/u", a, ["k"]) == 2
    assert st.upsert("d/u", a, ["k"]) == 0
    assert st.upsert("d/u", pd.DataFrame({"k": [2], "v": [99]}), ["k"]) == 0
    assert st.read("d/u").set_index("k")["v"].to_dict() == {1: 10, 2: 99}


def test_points_de_reprise_survivent_a_un_nouveau_processus(tmp_path):
    ParquetStore(tmp_path / "s").mark_done("job", "A")
    st2 = ParquetStore(tmp_path / "s")
    st2.mark_done("job", "B")
    assert st2.done_items("job") == {"A", "B"}
    st2.reset_job("job")
    assert st2.done_items("job") == set()


def test_points_de_reprise_jamais_dans_les_donnees_servies(tmp_path):
    """Les fichiers de reprise/journal ne sont pas des jeux de données (ni .parquet)."""
    st = ParquetStore(tmp_path / "s")
    st.mark_done("prices-2026-10-02", "SPY")
    st.log_event("prices", "SPY", "ok")
    assert st.datasets() == []


# ---------------------------------------------------------------------- prix : idempotence
def _yf(dates, closes):
    idx = pd.DatetimeIndex(pd.to_datetime(dates)).tz_localize("America/New_York")
    n = len(dates)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Volume": [1.0] * n, "Dividends": [0.0] * n, "Stock Splits": [0.0] * n},
                        index=idx)  # fmt: skip


def test_prix_update_deux_fois_ne_duplique_rien_et_ecarte_aujourd_hui(tmp_path):
    from datetime import date

    cfg = {"http": {"max_attempts": 2, "base_backoff_s": 0, "max_backoff_s": 0,
                    "sources": {"yfinance": {"min_interval_s": 0}}},
           "prices": {"history_start": "2024-01-01", "overlap_days": 5}}  # fmt: skip
    d = ["2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06"]  # 6 mars = « aujourd'hui »
    f = lambda tk, a, b: (_yf(d, [1.0, 2.0, 3.0, 4.0]), {"currency": "USD"})  # noqa: E731
    st = ParquetStore(tmp_path / "s")
    pc = PricesConnector(
        st, cfg, tmp_path / "c", fetcher=f, sleep=lambda s: None, today=date(2024, 3, 6)
    )
    r1 = pc.update("TK")
    r2 = pc.update("TK")
    out = st.read("prices/TK")
    assert out["date"].is_unique and out["date"].max() == pd.Timestamp("2024-03-05")
    assert r1["new_rows"] == 3 and r2["new_rows"] == 0 and not r2["restated"]


def test_prix_source_indisponible_leve_et_n_ecrit_pas(tmp_path):
    from datetime import date

    cfg = {"http": {"max_attempts": 2, "base_backoff_s": 0, "max_backoff_s": 0,
                    "sources": {"yfinance": {"min_interval_s": 0}}},
           "prices": {"history_start": "2024-01-01", "overlap_days": 5}}  # fmt: skip

    def f(tk, a, b):
        raise ConnectionError("réseau coupé")

    st = ParquetStore(tmp_path / "s")
    pc = PricesConnector(
        st, cfg, tmp_path / "c", fetcher=f, sleep=lambda s: None, today=date(2024, 3, 6)
    )
    with pytest.raises(RuntimeError):
        pc.update("TK")
    assert not st.exists("prices/TK")


# ---------------------------------------------------------------------- hygiène du code
def test_aucun_verify_false_ni_import_metier_ni_sdk_llm_ni_nom_de_modele():
    interdits_import = re.compile(
        r"^\s*(from|import)\s+(anthropic|openai|google\.generativeai|google\.genai|groq|ollama|"
        r"litellm|amundi_agentic\.(?!data)\w+)", re.M)  # fmt: skip
    noms_modeles = re.compile(r"(?i)\b(gemini-\d|llama\s?3|gpt-\d|claude-|mixtral|qwen)")
    for f in (SRC / "data").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        assert "verify=False" not in t.replace(" ", ""), f
        assert not interdits_import.search(t), f
        assert not noms_modeles.search(t), f
    assert not interdits_import.search(
        (SRC / "cli.py").read_text(encoding="utf-8").split("def main")[0]
    )


def test_aucun_secret_ecrit_dans_les_fichiers_du_depot_de_donnees():
    """Les motifs de clé (api_key=<valeur>) n'apparaissent dans aucun fichier suivi du dépôt."""
    racine = SRC.parents[1]
    motif = re.compile(r"api_key=(?!\*\*\*)[A-Za-z0-9]{16,}")
    for p in list((racine / "src").rglob("*.py")) + list((racine / "config").rglob("*.yaml")):
        assert not motif.search(p.read_text(encoding="utf-8")), p
