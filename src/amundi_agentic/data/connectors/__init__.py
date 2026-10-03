"""Connecteurs de sources gratuites. Chaque connecteur : réseau -> cache -> stockage Parquet."""

from __future__ import annotations

from amundi_agentic.data.http import HttpClient
from amundi_agentic.data.settings import DataSettings


def make_http_client(settings: DataSettings) -> HttpClient:
    cfg = settings.config["http"]
    return HttpClient(
        settings.cache_dir,
        min_intervals={k: v["min_interval_s"] for k, v in cfg["sources"].items()},
        max_attempts=cfg["max_attempts"],
        base_backoff_s=cfg["base_backoff_s"],
        max_backoff_s=cfg["max_backoff_s"],
        timeout_s=cfg["timeout_s"],
    )
