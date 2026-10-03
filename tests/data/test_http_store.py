"""Cache disque, débit, backoff, secrets (jamais dans le cache) ; stockage Parquet et reprise."""

from __future__ import annotations

import json

import pandas as pd
import pytest
import requests

from amundi_agentic.data.http import HttpClient, HttpError, redact
from amundi_agentic.data.store import ParquetStore


class FauxResp:
    def __init__(self, status=200, content=b"{}", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}
        self.text = content.decode()


class FausseSession:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.verify = True

    def get(self, url, params=None, headers=None, timeout=None, **kw):
        self.appels.append({"url": url, "params": params, "kw": kw})
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def client(tmp_path, reponses, **kw):
    pauses: list[float] = []
    s = FausseSession(reponses)
    c = HttpClient(
        tmp_path / "http", session=s, sleep=pauses.append, jitter=lambda: 0.0,
        clock=lambda: 0.0, **kw,
    )  # fmt: skip
    return c, s, pauses


def test_requete_identique_servie_par_le_cache(tmp_path):
    c, s, _ = client(tmp_path, [FauxResp(content=b'{"a": 1}')])
    r1 = c.get("x", "https://exemple.org/api", params={"q": 1})
    r2 = c.get("x", "https://exemple.org/api", params={"q": 1})
    assert not r1.from_cache and r2.from_cache and r2.json() == {"a": 1}
    assert len(s.appels) == 1  # un seul appel réseau


def test_cache_persiste_entre_clients(tmp_path):
    c1, _, _ = client(tmp_path, [FauxResp(content=b"abc")])
    c1.get("x", "https://exemple.org/a")
    c2, s2, _ = client(tmp_path, [])
    assert c2.get("x", "https://exemple.org/a").content == b"abc" and s2.appels == []


def test_secret_absent_du_cache_et_de_la_cle(tmp_path):
    c, _, _ = client(tmp_path, [FauxResp(content=b"{}"), FauxResp(content=b"{}")])
    c.get("fred", "https://exemple.org/f", params={"series_id": "X", "api_key": "SECRETVALEUR123"})
    # même requête, autre clé API : même entrée de cache (la clé ne participe pas à l'identité)
    r = c.get("fred", "https://exemple.org/f", params={"series_id": "X", "api_key": "AUTRE"})
    assert r.from_cache
    for f in (tmp_path / "http").rglob("*"):
        if f.is_file():
            assert b"SECRETVALEUR123" not in f.read_bytes()
    assert "SECRETVALEUR123" not in r.url and "api_key" not in r.url


def test_redact_motifs_et_valeur_d_environnement(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "VALEURTEST999")
    assert "VALEURTEST999" not in redact(
        "erreur sur https://x?api_key=VALEURTEST999&a=1 : VALEURTEST999"
    )
    assert "api_key=***" in redact("https://x?api_key=abc&b=2")


def test_erreur_reseau_ne_fuit_pas_la_cle(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "VALEURTEST999")
    exc = requests.ConnectionError("Failed https://x?api_key=VALEURTEST999")
    c, _, _ = client(tmp_path, [exc], max_attempts=1)
    with pytest.raises(HttpError) as e:
        c.get("fred", "https://x", params={"api_key": "VALEURTEST999"})
    assert "VALEURTEST999" not in str(e.value)


def test_backoff_exponentiel_sur_429_puis_succes(tmp_path):
    c, s, pauses = client(
        tmp_path, [FauxResp(429), FauxResp(503), FauxResp(content=b"ok")], base_backoff_s=2.0
    )
    assert c.get("x", "https://exemple.org/a").content == b"ok"
    assert pauses == [2.0, 4.0] and len(s.appels) == 3


def test_retry_after_respecte(tmp_path):
    c, _, pauses = client(tmp_path, [FauxResp(429, headers={"Retry-After": "17"}), FauxResp()])
    c.get("x", "https://exemple.org/a")
    assert pauses == [17.0]


def test_echec_definitif_apres_max_essais_non_mis_en_cache(tmp_path):
    c, s, _ = client(tmp_path, [FauxResp(429)] * 3, max_attempts=3)
    with pytest.raises(HttpError) as e:
        c.get("x", "https://exemple.org/a")
    assert e.value.status == 429 and len(s.appels) == 3
    assert not list((tmp_path / "http").rglob("*.bin"))


def test_404_non_rejoue(tmp_path):
    c, s, pauses = client(tmp_path, [FauxResp(404)])
    with pytest.raises(HttpError) as e:
        c.get("x", "https://exemple.org/a")
    assert e.value.status == 404 and len(s.appels) == 1 and pauses == []


def test_limitation_de_debit_par_source(tmp_path):
    horloge = iter([0.0, 0.05, 0.05, 0.05])  # appels à 0 puis 0,05 s
    pauses: list[float] = []
    s = FausseSession([FauxResp(), FauxResp()])
    c = HttpClient(tmp_path / "h", min_intervals={"edgar": 0.15}, session=s,
                   sleep=pauses.append, clock=lambda: next(horloge))  # fmt: skip
    c.get("edgar", "https://exemple.org/1")
    c.get("edgar", "https://exemple.org/2")
    assert pauses and pauses[0] == pytest.approx(0.10)  # 0,15 - 0,05 écoulé


def test_tls_jamais_desactive(tmp_path):
    c, s, _ = client(tmp_path, [FauxResp()])
    c.get("x", "https://exemple.org/a")
    assert "verify" not in s.appels[0]["kw"] and s.verify is True

    import amundi_agentic.data as pkg

    sources = "".join(
        p.read_text(encoding="utf-8")
        for p in __import__("pathlib").Path(pkg.__path__[0]).rglob("*.py")
    )
    assert "verify=False" not in sources and "verify = False" not in sources


def test_ttl_expire(tmp_path):
    c, s, _ = client(tmp_path, [FauxResp(content=b"1"), FauxResp(content=b"2")])
    c.get("x", "https://exemple.org/a", ttl_s=3600)
    assert c.get("x", "https://exemple.org/a", ttl_s=3600).from_cache
    assert not c.get("x", "https://exemple.org/a", ttl_s=-1).from_cache


# --------------------------------------------------------------------------- stockage


def test_ecriture_atomique_et_lecture(tmp_path):
    st = ParquetStore(tmp_path)
    df = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "v": [1.0]})
    st.write("a/b", df)
    assert st.read("a/b").equals(df) and not list(tmp_path.rglob("*.tmp*"))
    assert st.datasets("a") == ["a/b"] and st.read("absent") is None


def test_upsert_dedoublonne_et_garde_la_derniere_valeur(tmp_path):
    st = ParquetStore(tmp_path)
    d = pd.to_datetime(["2024-01-02", "2024-01-03"])
    assert st.upsert("p", pd.DataFrame({"date": d, "v": [1.0, 2.0]}), ["date"]) == 2
    nouveaux = st.upsert(
        "p",
        pd.DataFrame({"date": d[1:].append(pd.to_datetime(["2024-01-04"])), "v": [9.0, 3.0]}),
        ["date"],
    )
    out = st.read("p")
    assert nouveaux == 1 and out["v"].tolist() == [1.0, 9.0, 3.0]
    assert not out["date"].duplicated().any()


def test_points_de_reprise_et_journal(tmp_path):
    st = ParquetStore(tmp_path)
    assert st.done_items("job") == set()
    st.mark_done("job", "A")
    st.mark_done("job", "B")
    assert ParquetStore(tmp_path).done_items("job") == {"A", "B"}  # survit à un redémarrage
    st.log_event("prices", "SPY", "error", "x")
    st.log_event("prices", "SPY", "ok", "y")
    assert st.last_events()[("prices", "SPY")]["status"] == "ok"
    json.loads((tmp_path / "_status" / "events.jsonl").read_text().splitlines()[0])


def test_texte_compresse(tmp_path):
    st = ParquetStore(tmp_path)
    st.write_text("f/x", "bonjour é")
    assert st.read_text("f/x") == "bonjour é" and st.has_text("f/x") and st.read_text("f/y") is None
