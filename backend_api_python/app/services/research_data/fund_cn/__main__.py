"""CLI: python -m app.services.research_data.fund_cn ..."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.registry import LocalJsonRegistry

from .catalog import coverage_matrix, factor_ids, promote_factor_to_pit_safe, schema_hash
from .orchestrator import (
    run_compute_publish,
    run_coverage,
    run_pit_publish,
    run_pipeline,
    run_register,
    run_stage,
)
from .paths_local import default_staging_root


def _parse_dates(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


def _read_market_file(path: str) -> pd.DataFrame:
    """读取显式注入的未复权日行情文件；CSV/Parquet 共用同一列契约。"""
    source = Path(path)
    if source.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(source)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    raise ValueError("--market-file must be .parquet, .pq or .csv")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-share fund_cn_basic@v1 pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_catalog = sub.add_parser("catalog", help="Print factor catalog / coverage matrix")
    p_catalog.add_argument("--json", action="store_true")

    p_stage = sub.add_parser("stage", help="Fetch/stage statements (requires live adapters or skip)")
    p_stage.add_argument("--instruments", required=True, help="Comma-separated CNStock:xxxxxx")
    p_stage.add_argument("--root", default="")

    p_cov = sub.add_parser("coverage", help="Coverage gate report from staging")
    p_cov.add_argument("--root", default="")

    p_pit = sub.add_parser("pit", help="Publish staging → Canonical pit_fundamental")
    p_pit.add_argument("--root", default="")
    p_pit.add_argument("--canonical-root", default="")

    p_compute = sub.add_parser("compute", help="Build daily panels from staging PIT metrics")
    p_compute.add_argument("--instruments", required=True)
    p_compute.add_argument("--dates", required=True, help="Comma-separated YYYY-MM-DD")
    p_compute.add_argument(
        "--market-file",
        required=True,
        help="CSV/Parquet with instrument_key,trading_date,unadjusted close",
    )
    p_compute.add_argument("--root", default="")
    p_compute.add_argument("--all", action="store_true", help="Include compute_ok factors beyond MVP")

    p_reg = sub.add_parser("register", help="Register MVP factors into LocalJson Factor Lab registry")
    p_reg.add_argument("--registry-root", default="")
    p_reg.add_argument(
        "--allow-uncovered",
        action="store_true",
        help="Bypass staging coverage gate (unsafe; intended only for diagnostics)",
    )

    p_promote = sub.add_parser("promote", help="Mark factor gates ok after audit (Phase 3)")
    p_promote.add_argument("--factor-id", required=True)

    p_pipe = sub.add_parser("pipeline", help="Offline demo pipeline needs injected data via Python API")
    p_pipe.add_argument("--help-api", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "catalog":
        matrix = coverage_matrix()
        if args.json:
            print(json.dumps({"schema_hash": schema_hash(), "factors": matrix}, ensure_ascii=False, indent=2))
        else:
            print(f"factor_set schema_hash={schema_hash()} count={len(matrix)}")
            for row in matrix:
                print(
                    f"{row['factor_id']:28} mvp={row['mvp']} "
                    f"RAW={row['RAW_OK']} COMPUTE={row['COMPUTE_OK']} PIT={row['PIT_OK']} "
                    f"policy={row['information_policy']}"
                )
        return 0

    root = Path(args.root) if getattr(args, "root", "") else default_staging_root()

    if args.cmd == "stage":
        keys = [k.strip() for k in args.instruments.split(",") if k.strip()]
        from .adapters.share_capital import CninfoShareCapitalAdapter

        info = run_stage(keys, root=root, share_capital_adapter=CninfoShareCapitalAdapter())
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.cmd == "coverage":
        print(json.dumps(run_coverage(root), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.cmd == "pit":
        store = LocalCanonicalStore(Path(args.canonical_root) if args.canonical_root else None)
        print(json.dumps(run_pit_publish(store=store, root=root), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.cmd == "compute":
        keys = [k.strip() for k in args.instruments.split(",") if k.strip()]
        dates = _parse_dates(args.dates)
        result = run_compute_publish(
            dates,
            keys,
            market=_read_market_file(args.market_file),
            root=root,
            mvp_only=not args.all,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.cmd == "register":
        reg = LocalJsonRegistry(Path(args.registry_root) if args.registry_root else None)
        refs = run_register(
            reg,
            root=root,
            require_coverage=not args.allow_uncovered,
        )
        print(json.dumps({"registered": refs, "mvp_ids": factor_ids(mvp_only=True)}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "promote":
        factor = promote_factor_to_pit_safe(args.factor_id)
        print(
            json.dumps(
                {
                    "factor_id": factor.factor_id,
                    "RAW_OK": factor.raw_ok,
                    "COMPUTE_OK": factor.compute_ok,
                    "PIT_OK": factor.pit_ok,
                    "all_gates_ok": factor.all_gates_ok,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.cmd == "pipeline":
        print(
            "Use orchestrator.run_pipeline(..., statement_rows=..., announce_rows=...) "
            "for offline runs; live stage uses AKShare adapters."
        )
        # Keep import referenced for operators discovering the API.
        _ = run_pipeline
        _ = date
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
