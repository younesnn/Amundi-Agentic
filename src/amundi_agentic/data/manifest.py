"""Manifeste des données (rejouabilité) : hash de chaque jeu, versions, hash des configs.

`data_manifest(settings)` est réutilisable par les phases suivantes (le pré-enregistrement D-027
y liera son hash). Deux appels sur le même stockage donnent le même manifeste (hors `generated_at`,
exclu du hash) ; modifier un octet d'un jeu ou d'une config change `manifest_sha256`.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import pyarrow.parquet as pq

from amundi_agentic.data.settings import CONFIG_DIR, DataSettings
from amundi_agentic.data.store import ParquetStore

LIBS = ("pandas", "pyarrow", "yfinance", "requests", "feedparser")
DATE_COLS = ("date", "published_at", "accepted_utc", "observed_at", "filed", "week_start")
CONFIGS = ("data.yaml", "universe.yaml", "esg.yaml")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _event_key(ds: str) -> tuple[str, str] | None:
    parts = ds.split("/")
    if parts[0] == "prices" and len(parts) == 2:
        return ("prices", parts[1])
    if ds.startswith("macro/fred/"):
        return ("fred", parts[2])
    if ds.startswith("macro/ecb/"):
        return ("ecb", parts[2])
    if parts[0] == "fx" and len(parts) == 2:
        return ("fx", parts[1].removeprefix("EXR_"))
    if ds.startswith("filings/index/"):
        return ("edgar", parts[2])
    if parts[0] == "xbrl" and len(parts) == 2:
        return ("xbrl", parts[1])
    return None


def _describe(p: Path) -> dict:
    meta = pq.ParquetFile(p).metadata
    info: dict = {"rows": meta.num_rows, "date_min": None, "date_max": None}
    noms = pq.ParquetFile(p).schema_arrow.names
    col = next((c for c in DATE_COLS if c in noms), None)
    if col and meta.num_rows:
        s = pq.read_table(p, columns=[col]).to_pandas()[col].dropna()
        if len(s):
            info["date_min"], info["date_max"] = str(s.min()), str(s.max())
    return info


def _entries(root: Path, kind: str, events: dict, origins: bool) -> list[dict]:
    sortie = []
    if not root.exists():
        return sortie
    for p in sorted(root.rglob("*.parquet")):
        rel = p.relative_to(root).as_posix()
        e = {"kind": kind, "path": rel, "sha256": sha256_file(p), **_describe(p)}
        if kind == "derive":
            ev = events.get(_event_key(rel.removesuffix(".parquet")) or ("", ""))
            e["fetched_at"] = ev["at"] if ev else None
        elif origins:
            side = p.parent / "_origin.json"
            info = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
            e["origin"] = info.get(p.name, {}).get("origin", "collecte")
            e["fetched_at"] = p.parent.name  # date de collecte (dossier daté)
        sortie.append(e)
    return sortie


def data_manifest(settings: DataSettings) -> dict:
    """Manifeste déterministe du stockage dérivé, des instantanés et des configurations."""
    store = ParquetStore(settings.store_dir)
    events = store.last_events()
    contenu = {
        "versions": {
            "python": platform.python_version(),
            **{lib: metadata.version(lib) for lib in LIBS},
        },
        "config_sha256": {
            n: sha256_file(CONFIG_DIR / n) for n in CONFIGS if (CONFIG_DIR / n).is_file()
        },
        "datasets": _entries(settings.store_dir, "derive", events, False)
        + _entries(settings.snapshot_dir, "snapshot", events, True),
    }
    canon = json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {
        **contenu,
        "manifest_sha256": hashlib.sha256(canon).hexdigest(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),  # hors hash
    }


def write_manifest(settings: DataSettings, path: Path | None = None) -> Path:
    path = path or settings.data_dir / "data_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data_manifest(settings), ensure_ascii=False, indent=1), "utf-8")
    return path
