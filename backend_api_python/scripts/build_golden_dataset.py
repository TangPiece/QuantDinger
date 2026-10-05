#!/usr/bin/env python3
"""构建 Golden Dataset cn_stock_daily@v1。

默认写 LocalCanonicalStore（CI / 离线）；`--use-r2` 写 R2。
默认 `--fixture` 不依赖外网；加 `--from-source` 经 DataSource 拉真源。

用法（在 backend_api_python 下）::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/build_golden_dataset.py \\
      --start 2020-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def _parse_date(text: str) -> date:
    return date.fromisoformat(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cn_stock_daily@v1 Golden Dataset")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--universe-code", default="CSI300")
    parser.add_argument("--universe-version", default=None)
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument(
        "--instruments",
        default="CNStock:000001,CNStock:000002,CNStock:600000",
        help="comma-separated instrument_key list",
    )
    parser.add_argument("--local-root", default=None, help="LocalCanonicalStore root")
    parser.add_argument("--registry-root", default=None, help="LocalJsonRegistry root")
    parser.add_argument("--use-r2", action="store_true", help="Write via R2CanonicalStore")
    parser.add_argument(
        "--from-source",
        action="store_true",
        help="Pull market via DataSourceFactory (network); default uses fixture",
    )
    parser.add_argument(
        "--status",
        default="validated",
        help="Registry dataset status (default validated)",
    )
    args = parser.parse_args()

    from app.services.research_data.canonical_store import (
        CachingCanonicalStore,
        LocalCanonicalStore,
        R2CanonicalStore,
    )
    from app.services.research_data.ingest.build_golden import build_golden_dataset
    from app.services.research_data.registry import LocalJsonRegistry, get_default_registry

    if args.use_r2:
        remote = R2CanonicalStore()
        local = LocalCanonicalStore(
            root=Path(args.local_root) if args.local_root else None
        )
        store = CachingCanonicalStore(remote=remote, local=local)
        registry = get_default_registry()
    else:
        root = Path(args.local_root) if args.local_root else None
        store = LocalCanonicalStore(root=root)
        if args.registry_root:
            registry = LocalJsonRegistry(root=Path(args.registry_root))
        else:
            # 离线默认本地 Registry，避免误连未配置的 D1
            registry = LocalJsonRegistry(
                root=Path(args.registry_root)
                if args.registry_root
                else (store.root.parent / "registry")
            )

    instruments = [x.strip() for x in args.instruments.split(",") if x.strip()]
    result = build_golden_dataset(
        store,
        registry,
        instrument_keys=instruments,
        start=_parse_date(args.start),
        end=_parse_date(args.end),
        universe_code=args.universe_code,
        universe_version=args.universe_version,
        snapshot_id=args.snapshot_id,
        use_fixture=not args.from_source,
        status=args.status,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
