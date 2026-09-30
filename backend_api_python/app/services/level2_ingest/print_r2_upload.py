"""Print aws s3 sync commands for manual R2 upload from staging parquet."""
from __future__ import annotations

import argparse

from . import config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print manual R2 upload commands")
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)

    staging = config.STAGING_PARQUET / args.date
    if not staging.is_dir():
        print(f"missing staging: {staging}")
        print(f"run: .venv/bin/python -m storage.convert_local --date {args.date}")
        return 1

    n = sum(1 for p in staging.rglob("*.parquet"))
    print(f"local parquet: {staging} ({n} files)")
    print(f"R2 prefix: {config.R2_PREFIX}/{args.date}/")
    print()
    print("full upload (overwrites old partial on R2):")
    print(f"  aws s3 sync {staging}/ s3://{config.R2_BUCKET}/{config.R2_PREFIX}/{args.date}/ \\")
    print('    --endpoint-url "$R2_ENDPOINT_URL"')
    print()
    print("after upload, sync R2 catalog only:")
    print(
        f"  STORAGE_BACKEND=r2 .venv/bin/python -m storage.sync_catalog "
        f"--date {args.date} --backend r2 --verify --upload-remote"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
