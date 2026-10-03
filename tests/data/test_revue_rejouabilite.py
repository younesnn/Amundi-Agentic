"""Revue indépendante (D-043) : instantanés append-only, manifeste, rejouabilité, PIT inchangé."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from data_helpers import prix

from amundi_agentic.data import manifest as mf
from amundi_agentic.data.connectors.prices import PricesConnector
from amundi_agentic.data.manifest import data_manifest
from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import DataSettings
from amundi_agentic.data.store import ParquetStore, rebuild_snapshots_from_store

ROOT = Path(__file__).resolve().parents[2]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Horloge:
    def __init__(self, jour="2026-03-01"):
        self.jour = jour

    def __call__(self):
        return datetime.fromisoformat(self.jour).replace(tzinfo=UTC)


def mk(tmp_path, jour="2026-03-01"):
    h = Horloge(jour)
    return ParquetStore(tmp_path / "store", tmp_path / "snap", clock=h), h


def df(v):
    return pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-03"]), "close": [1.0, v]})


# ---------------------------------------------------------------- instantanés append-only
def test_instantane_jamais_ecrase_suffixes_et_idempotence(tmp_path):
    st, _ = mk(tmp_path)
    p1 = st.snapshot("prices", "X", df(2.0))
    h1 = sha(p1)
    assert st.snapshot("prices", "X", df(2.0)) == p1  # identique : no-op
    p2 = st.snapshot("prices", "X", df(2.0 + 1e-9))  # différent d'un seul chiffre
    assert p2.name == "X~2.parquet" and p2 != p1
    assert st.snapshot("prices", "X", df(2.0 + 1e-9)) == p2  # idempotent aussi sur ~2
    p3 = st.snapshot("prices", "X", df(5.0))
    assert p3.name == "X~3.parquet"
    assert st.snapshot("prices", "X", df(2.0)) == p1  # retour à l'ancien contenu : pas de ~4
    assert sha(p1) == h1  # l'original est resté identique octet pour octet
    assert len(list(p1.parent.glob("X*.parquet"))) == 3
    lu = st.read_snapshots("prices", "X")
    assert len(lu) == 6 and set(lu["origin"]) == {"collecte"}


def test_instantane_autre_jour_nouveau_dossier_et_ancien_intact(tmp_path):
    st, h = mk(tmp_path)
    p1 = st.snapshot("prices", "X", df(2.0))
    h1 = sha(p1)
    h.jour = "2026-03-02"
    p2 = st.snapshot("prices", "X", df(9.0))
    assert p2.parent.name == "2026-03-02" and sha(p1) == h1
    assert (
        st.read_snapshots("prices", "X")["snapshot_date"].tolist()
        == ["2026-03-01"] * 2 + ["2026-03-02"] * 2
    )


def test_instantane_ne_confond_pas_deux_noms_a_prefixe_commun(tmp_path):
    st, _ = mk(tmp_path)
    st.snapshot("prices", "AB", df(1.0))
    st.snapshot("prices", "ABC", df(7.0))
    assert len(st.read_snapshots("prices", "AB")) == 2


def test_instantane_ecriture_atomique(tmp_path, monkeypatch):
    st, _ = mk(tmp_path)
    p1 = st.snapshot("prices", "X", df(2.0))
    h1 = sha(p1)

    def boom(self, *a, **k):
        raise OSError("disque plein")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)
    with pytest.raises(OSError):
        st.snapshot("prices", "X", df(3.0))
    monkeypatch.undo()
    assert sha(p1) == h1 and not (p1.parent / "X~2.parquet").exists()


def test_instantane_reconstruit_etiquete_et_jamais_confondu_avec_une_collecte(tmp_path):
    st, h = mk(tmp_path)
    st.write("prices/X", df(2.0))
    rebuild_snapshots_from_store(st)
    lu = st.read_snapshots("prices", "X")
    assert set(lu["origin"]) == {"reconstruit_depuis_le_stockage"}
    meta = json.loads((tmp_path / "snap" / "prices" / "2026-03-01" / "_origin.json").read_text())
    assert meta["X.parquet"]["origin"] == "reconstruit_depuis_le_stockage"
    rebuild_snapshots_from_store(st)  # idempotent
    assert len(list((tmp_path / "snap" / "prices" / "2026-03-01").glob("X*.parquet"))) == 1
    # une vraie collecte différente le même jour : sous ~2, étiquetée « collecte »
    st.snapshot("prices", "X", df(3.0))
    lu = st.read_snapshots("prices", "X")
    assert sorted(set(lu["origin"])) == ["collecte", "reconstruit_depuis_le_stockage"]
    # une collecte ne peut pas réétiqueter un instantané reconstruit existant
    meta = json.loads((tmp_path / "snap" / "prices" / "2026-03-01" / "_origin.json").read_text())
    assert meta["X.parquet"]["origin"] == "reconstruit_depuis_le_stockage"
    assert meta["X~2.parquet"]["origin"] == "collecte"


def test_retraitement_yahoo_retroactif_retrouvable(tmp_path):
    """Un split rétroactif change tout l'historique : les deux versions restent lisibles."""
    cfg = {"http": {"max_attempts": 2, "base_backoff_s": 0, "max_backoff_s": 0,
                    "sources": {"yfinance": {"min_interval_s": 0}}},
           "prices": {"history_start": "2024-01-01", "overlap_days": 5}}  # fmt: skip
    etat = {"f": 1.0}
    d = ["2024-03-01", "2024-03-04", "2024-03-05"]

    def fetch(tk, a, b):
        idx = pd.DatetimeIndex(pd.to_datetime(d)).tz_localize("America/New_York")
        c = [100.0 * etat["f"], 101.0 * etat["f"], 102.0 * etat["f"]]
        return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": [1.0] * 3,
                             "Dividends": [0.0] * 3, "Stock Splits": [0.0] * 3}, index=idx), {}  # fmt: skip

    st, h = mk(tmp_path)
    pc = PricesConnector(st, cfg, tmp_path / "c", fetcher=fetch, sleep=lambda s: None,
                         today=date(2024, 3, 6))  # fmt: skip
    pc.update("TK")
    etat["f"] = 0.5  # split 2:1 rétroactif : tout l'historique est divisé
    pc2 = PricesConnector(st, cfg, tmp_path / "c", fetcher=fetch, sleep=lambda s: None,
                          today=date(2024, 3, 7))  # fmt: skip
    r = pc2.update("TK")
    assert r["restated"]
    lu = st.read_snapshots("prices", "TK")
    ancien = lu[lu["date"] == "2024-03-01"]["close"].tolist()
    assert sorted(ancien) == [50.0, 100.0]  # les deux versions de la même barre sont conservées
    assert st.read("prices/TK")["close"].iloc[0] == 50.0


# ---------------------------------------------------------------- manifeste
@pytest.fixture
def reglages(tmp_path, cfg, monkeypatch):
    conf = tmp_path / "config"
    conf.mkdir()
    for n in mf.CONFIGS:
        shutil.copy(ROOT / "config" / n, conf / n)
    monkeypatch.setattr(mf, "CONFIG_DIR", conf)
    s = DataSettings(data_dir=tmp_path / "d", config=cfg)
    st = ParquetStore(s.store_dir, s.snapshot_dir, clock=Horloge())
    st.write("prices/X", df(2.0))
    st.write("macro/fred/Y", df(4.0))
    st.snapshot("prices", "X", df(2.0))
    return s, st, conf


def test_manifeste_stable_et_independant_de_generated_at(reglages, monkeypatch):
    s, _, _ = reglages
    m1 = data_manifest(s)

    class Faux(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2031, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(mf, "datetime", Faux)
    m2 = data_manifest(s)
    assert m1["generated_at"] != m2["generated_at"]
    assert m1["manifest_sha256"] == m2["manifest_sha256"]
    # le hash est bien celui du contenu canonique recalculé à la main
    contenu = {k: m1[k] for k in ("versions", "config_sha256", "datasets")}
    canon = json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode()
    assert hashlib.sha256(canon).hexdigest() == m1["manifest_sha256"]


def test_manifeste_sensible_a_un_octet_une_config_une_version(reglages, monkeypatch):
    s, st, conf = reglages
    base = data_manifest(s)["manifest_sha256"]
    # 1) un seul chiffre d'une seule valeur du jeu dérivé
    st.write("prices/X", df(2.0 + 1e-12))
    m = data_manifest(s)["manifest_sha256"]
    assert m != base
    st.write("prices/X", df(2.0))
    assert data_manifest(s)["manifest_sha256"] == base  # retour à l'état initial : même hash
    # 2) un octet brut du fichier : soit le hash change, soit le manifeste refuse de lire
    p = st.path("prices/X")
    brut = bytearray(p.read_bytes())
    brut[len(brut) // 2] ^= 0x01
    p.write_bytes(bytes(brut))
    try:
        apres = data_manifest(s)["manifest_sha256"]
    except Exception:  # noqa: BLE001 - fichier corrompu : détecté par échec de lecture
        apres = None
    assert apres is None or apres != base
    st.write("prices/X", df(2.0))
    # 3) une configuration
    c = conf / "data.yaml"
    c.write_text(c.read_text(encoding="utf-8") + "\n# x\n", encoding="utf-8")
    assert data_manifest(s)["manifest_sha256"] != base
    c.write_text(c.read_text(encoding="utf-8").replace("\n# x\n", ""), encoding="utf-8")
    assert data_manifest(s)["manifest_sha256"] == base
    # 4) une version de bibliothèque
    vrai = mf.metadata.version
    monkeypatch.setattr(mf.metadata, "version", lambda n: "0.0.0" if n == "pandas" else vrai(n))
    assert data_manifest(s)["manifest_sha256"] != base


def test_manifeste_sensible_aux_instantanes_et_a_leur_origine(reglages, tmp_path):
    s, st, _ = reglages
    base = data_manifest(s)["manifest_sha256"]
    st.snapshot("prices", "X", df(9.0))  # nouvel instantané ~2
    assert data_manifest(s)["manifest_sha256"] != base
    m = data_manifest(s)
    origines = {d["path"]: d.get("origin") for d in m["datasets"] if d["kind"] == "snapshot"}
    assert set(origines.values()) == {"collecte"}
    rebuild_snapshots_from_store(st)
    m = data_manifest(s)
    origines = {d["path"]: d.get("origin") for d in m["datasets"] if d["kind"] == "snapshot"}
    assert "reconstruit_depuis_le_stockage" in origines.values()  # visible dans le manifeste


def test_manifeste_ordre_de_creation_sans_effet(tmp_path, cfg, monkeypatch):
    conf = tmp_path / "config"
    conf.mkdir()
    for n in mf.CONFIGS:
        shutil.copy(ROOT / "config" / n, conf / n)
    monkeypatch.setattr(mf, "CONFIG_DIR", conf)
    hs = []
    for ordre in (("a", "b", "c"), ("c", "a", "b")):
        s = DataSettings(data_dir=tmp_path / "_".join(ordre), config=cfg)
        st = ParquetStore(s.store_dir)
        for n in ordre:
            st.write(f"prices/{n}", df(1.0))
        hs.append(data_manifest(s)["manifest_sha256"])
    assert hs[0] == hs[1]


def test_manifeste_sans_cle_ni_chemin_personnel(reglages, monkeypatch, tmp_path):
    s, _, _ = reglages
    monkeypatch.setenv("FRED_API_KEY", "FAUXSECRET0123456789")
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Fictif fictif@exemple.org")
    txt = json.dumps(data_manifest(s))
    for interdit in (
        "FAUXSECRET0123456789",
        "fictif@exemple.org",
        str(tmp_path),
        "/Users/",
        "api_key",
    ):
        assert interdit not in txt
    assert not re.search(r"[A-Za-z]:\\\\|/home/", txt)


# ---------------------------------------------------------------- PIT inchangé
def test_as_of_ignore_les_instantanes_meme_collectes_apres_t(tmp_path, cfg):
    st, h = mk(tmp_path, "2030-01-01")  # collecte très postérieure à t
    st.write("prices/OK", prix(pd.bdate_range("2024-01-01", periods=10), list(range(1, 11))))
    futur = prix(pd.bdate_range("2024-01-01", periods=60), [999.0] * 60)
    st.snapshot("prices", "OK", futur)
    st.snapshot("prices", "ONLYSNAP", futur)  # ticker connu SEULEMENT par un instantané
    st.snapshot(
        "esg",
        "OK",
        pd.DataFrame({"asset_id": ["OK"], "observed_at": [pd.Timestamp("2030-01-01", tz="UTC")]}),
    )
    v = PointInTimeStore(st, cfg).as_of(date(2024, 1, 10))
    out = v.prices(["OK"])
    assert out.index.max() < pd.Timestamp("2024-01-10") and (out["OK"] < 900).all()
    with pytest.raises(KeyError):  # pas de repli sur les instantanés
        v.prices(["ONLYSNAP"])
    assert v.esg("OK") is None


def test_pit_n_importe_jamais_les_instantanes():
    src = (ROOT / "src" / "amundi_agentic" / "data" / "pit.py").read_text(encoding="utf-8")
    assert "snapshot" not in src.lower()
