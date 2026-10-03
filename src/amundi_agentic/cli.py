"""Interface en ligne de commande (D-010). Phase 2 : sous-commande `data`.

amundi-agentic data fetch --sources prices,fx,macro,filings,news,esg,pool
amundi-agentic data coverage
"""

from __future__ import annotations

import argparse
import json
import logging


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="amundi-agentic")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("data", help="couche de données")
    dsub = d.add_subparsers(dest="action", required=True)
    f = dsub.add_parser("fetch", help="télécharge les sources (reprise et cache)")
    f.add_argument("--sources", default="prices,fx,macro,filings,news,esg")
    f.add_argument("--tickers", default=None, help="titres séparés par des virgules")
    f.add_argument("--no-resume", action="store_true")
    f.add_argument(
        "--gdelt-weeks", type=int, default=0, help="sondage hebdomadaire GDELT par titre"
    )
    dsub.add_parser("coverage", help="génère docs/couverture_donnees.md")
    dsub.add_parser("snapshot", help="instantanés reconstruits depuis le stockage (sans réseau)")
    dsub.add_parser("manifest", help="écrit data_manifest.json")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from amundi_agentic.data.settings import DataSettings

    settings = DataSettings.load()
    if args.cmd == "data" and args.action == "fetch":
        from amundi_agentic.data.pipeline import run_fetch

        tickers = args.tickers.split(",") if args.tickers else None
        res = run_fetch(
            settings,
            args.sources.split(","),
            stock_tickers=tickers,
            resume=not args.no_resume,
            gdelt_weeks=args.gdelt_weeks,
        )
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 1 if any(v["error"] for v in res.values()) else 0
    if args.cmd == "data" and args.action == "snapshot":
        from amundi_agentic.data.store import ParquetStore, rebuild_snapshots_from_store

        n = rebuild_snapshots_from_store(ParquetStore(settings.store_dir, settings.snapshot_dir))
        print(json.dumps(n))
        return 0
    if args.cmd == "data" and args.action == "manifest":
        from amundi_agentic.data.manifest import write_manifest

        print(f"manifeste écrit : {write_manifest(settings)}")
        return 0
    if args.cmd == "data" and args.action == "coverage":
        from amundi_agentic.data.coverage import write_report

        print(f"rapport écrit : {write_report(settings)}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
