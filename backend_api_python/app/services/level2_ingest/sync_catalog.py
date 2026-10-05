"""Sync catalog from remote storage; verify R2/Baidu upload progress."""
from __future__ import annotations

import argparse

from . import catalog, config, object_store

_MIN_EQUITY_FILES = 10_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync or verify catalog per backend")
    parser.add_argument("--date", help="trade date YYYYMMDD")
    parser.add_argument("--backend", choices=("r2", "baidu"), default=None)
    parser.add_argument("--upload-remote", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--migrate-legacy", action="store_true")
    args = parser.parse_args(argv)

    if args.migrate_legacy:
        moved = catalog.migrate_legacy_catalogs()
        print("migrated to catalogs/r2/:", moved)
        return 0

    if not args.date:
        parser.error("--date is required unless --migrate-legacy")

    backend = args.backend or object_store.backend()
    if not object_store.is_configured(backend):
        print(f"{backend} not configured")
        return 2

    keys = catalog.sync_from_remote_prefix(args.date, backend=backend)
    parquet_keys = [k for k in keys if k.endswith(".parquet")]
    print(f"[{args.date}] {backend} synced {len(parquet_keys)} parquet keys")
    print(f"  local: {config.local_catalog_path(args.date, backend=backend)}")

    if args.upload_remote:
        catalog.upload_catalog(args.date, backend=backend)
        print(f"  remote: {config.catalog_object_key(args.date, backend=backend)}")

    if args.verify:
        ok = len(parquet_keys) >= _MIN_EQUITY_FILES
        print(f"  verify: {'OK' if ok else 'FAIL'} count={len(parquet_keys)} need>={_MIN_EQUITY_FILES}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
