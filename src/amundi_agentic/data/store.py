"""Stockage local en Parquet (choix justifié dans DECISIONS.md : D-0xx proposé).

Un fichier Parquet par jeu de données (`prices/SPY`, `macro/fred/DGS10`...). Écritures atomiques
(fichier temporaire puis remplacement), upsert sur clé, journal d'événements et points de reprise.
"""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


class ParquetStore:
    def __init__(
        self,
        root: Path,
        snapshot_root: Path | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # instantanés bruts append-only (None : désactivés, ex. tests unitaires de connecteurs)
        self.snapshot_root = Path(snapshot_root) if snapshot_root else None
        self._clock = clock

    # ------------------------------------------------------------------ instantanés append-only
    def snapshot(
        self, source: str, name: str, df: pd.DataFrame, origin: str = "collecte", note: str = ""
    ) -> Path | None:
        """Écrit les données brutes reçues dans `snapshots/<source>/<AAAA-MM-JJ>/<name>.parquet`.

        Jamais écrasé ni modifié : un contenu identique le même jour est un no-op (idempotent) ;
        un contenu différent le même jour est écrit sous `<name>~2.parquet`, `~3`...
        `origin` : « collecte » (reçu du réseau) ou « reconstruit_depuis_le_stockage ».
        """
        if self.snapshot_root is None or df is None:
            return None
        jour = self._clock().date().isoformat()
        d = self.snapshot_root / source / jour
        d.mkdir(parents=True, exist_ok=True)
        base = name.replace("/", "__")
        k, cible = 1, d / f"{base}.parquet"
        while cible.exists():
            if pd.read_parquet(cible).reset_index(drop=True).equals(df.reset_index(drop=True)):
                return cible
            k += 1
            cible = d / f"{base}~{k}.parquet"
        tmp = cible.with_name(cible.name + f".tmp{os.getpid()}")
        df.to_parquet(tmp, engine="pyarrow", index=False)
        os.replace(tmp, cible)
        side = d / "_origin.json"
        info = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
        info[cible.name] = {"origin": origin, "note": note, "rows": len(df)}
        side.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        return cible

    def read_snapshots(self, source: str, name: str) -> pd.DataFrame:
        """Tous les instantanés d'un jeu, avec colonnes snapshot_date et origin (ordre chronologique)."""
        morceaux = []
        base = self.snapshot_root / source if self.snapshot_root else None
        if base is None or not base.exists():
            return pd.DataFrame()
        pref = name.replace("/", "__")
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            side = d / "_origin.json"
            info = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
            for f in sorted(d.glob(f"{pref}*.parquet")):
                if f.stem.split("~")[0] != pref:
                    continue
                df = pd.read_parquet(f)
                df["snapshot_date"] = d.name
                df["origin"] = info.get(f.name, {}).get("origin", "collecte")
                morceaux.append(df)
        return pd.concat(morceaux, ignore_index=True) if morceaux else pd.DataFrame()

    # ------------------------------------------------------------------ Parquet
    def path(self, dataset: str) -> Path:
        return self.root / f"{dataset}.parquet"

    def exists(self, dataset: str) -> bool:
        return self.path(dataset).is_file()

    def read(self, dataset: str) -> pd.DataFrame | None:
        p = self.path(dataset)
        return pd.read_parquet(p) if p.is_file() else None

    def write(self, dataset: str, df: pd.DataFrame) -> None:
        p = self.path(dataset)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".tmp{os.getpid()}")
        df.to_parquet(tmp, engine="pyarrow", index=False)
        os.replace(tmp, p)

    def upsert(self, dataset: str, df: pd.DataFrame, key: list[str]) -> int:
        """Fusionne `df` dans le jeu ; la dernière ligne l'emporte sur une clé identique.

        Retourne le nombre de lignes nouvelles (clés absentes du jeu existant).
        """
        ancien = self.read(dataset)
        if ancien is None or ancien.empty:
            fusion = df.drop_duplicates(subset=key, keep="last")
            self.write(dataset, fusion.sort_values(key).reset_index(drop=True))
            return len(fusion)
        fusion = pd.concat([ancien, df], ignore_index=True)
        fusion = fusion.drop_duplicates(subset=key, keep="last").sort_values(key)
        fusion = fusion.reset_index(drop=True)
        nouvelles = len(fusion) - len(ancien)
        self.write(dataset, fusion)
        return nouvelles

    def datasets(self, prefix: str = "") -> list[str]:
        base = self.root / prefix if prefix else self.root
        if not base.exists():
            return []
        return sorted(
            p.relative_to(self.root).with_suffix("").as_posix() for p in base.rglob("*.parquet")
        )

    # ------------------------------------------------------------------ texte compressé
    def write_text(self, rel: str, text: str) -> None:
        p = self.root / f"{rel}.txt.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".tmp{os.getpid()}")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)

    def read_text(self, rel: str) -> str | None:
        p = self.root / f"{rel}.txt.gz"
        if not p.is_file():
            return None
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return f.read()

    def has_text(self, rel: str) -> bool:
        return (self.root / f"{rel}.txt.gz").is_file()

    # ------------------------------------------------------------------ reprise
    def _job_path(self, job: str) -> Path:
        return self.root / "_jobs" / f"{job}.json"

    def done_items(self, job: str) -> set[str]:
        p = self._job_path(job)
        return set(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else set()

    def mark_done(self, job: str, item: str) -> None:
        items = self.done_items(job) | {item}
        p = self._job_path(job)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(sorted(items)), encoding="utf-8")
        os.replace(tmp, p)

    def reset_job(self, job: str) -> None:
        self._job_path(job).unlink(missing_ok=True)

    # ------------------------------------------------------------------ journal d'événements
    def log_event(self, source: str, item: str, status: str, detail: str = "") -> None:
        """Ajoute un événement (ok, error, unavailable). `detail` doit déjà être expurgé de secrets."""
        p = self.root / "_status" / "events.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        ligne = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source": source,
            "item": item,
            "status": status,
            "detail": detail[:500],
        }
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def last_events(self) -> dict[tuple[str, str], dict]:
        p = self.root / "_status" / "events.jsonl"
        if not p.is_file():
            return {}
        derniers: dict[tuple[str, str], dict] = {}
        for ligne in p.read_text(encoding="utf-8").splitlines():
            if ligne.strip():
                ev = json.loads(ligne)
                derniers[(ev["source"], ev["item"])] = ev
        return derniers


def rebuild_snapshots_from_store(store: ParquetStore) -> dict[str, int]:
    """Initialise des instantanés depuis le stockage dérivé, SANS réseau.

    Étiquetés « reconstruit_depuis_le_stockage » : ils figent l'état actuel (après d'éventuels
    retraitements passés), pas ce qui a été reçu à l'origine.
    """
    jour = store._clock().date().isoformat()
    n: dict[str, int] = {}
    for ds in store.datasets():
        if ds.startswith("_"):
            continue
        df = store.read(ds)
        if df is None:
            continue
        source, _, reste = ds.partition("/")
        store.snapshot(
            source, reste or source, df, "reconstruit_depuis_le_stockage",
            f"reconstruit depuis le stockage le {jour}",
        )  # fmt: skip
        n[source] = n.get(source, 0) + 1
    return n
