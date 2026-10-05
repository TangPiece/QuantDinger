#!/usr/bin/env python3
"""将 PG Universe 导出为研究 Canonical Snapshot。

用法（在 backend_api_python 下）::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/export_universe_snapshot.py \\
      --universe-code CSI300 --version 2026.10.05 \\
      --start 2020-01-01 --end 2026-10-05
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 避免拉起完整 Flask app（脚本可只连库）
os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export PG universe to research snapshot")
    parser.add_argument("--universe-code", required=True)
    parser.add_argument("--version", required=True, help="universe_version, e.g. 2026.10.05")
    parser.add_argument("--start", default="1900-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--local-root", default=None, help="LocalCanonicalStore root for offline")
    parser.add_argument("--use-r2", action="store_true", help="Write via R2CanonicalStore")
    args = parser.parse_args()

    from app.services.research_data.canonical_store import LocalCanonicalStore, R2CanonicalStore
    from app.services.research_data.registry import get_default_registry
    from app.services.research_data.universe_export import export_universe_snapshot

    if args.use_r2:
        store = R2CanonicalStore()
    else:
        root = Path(args.local_root) if args.local_root else None
        store = LocalCanonicalStore(root=root)

    registry = get_default_registry()
    result = export_universe_snapshot(
        store=store,
        registry=registry,
        universe_code=args.universe_code,
        universe_version=args.version,
        user_id=args.user_id,
        start=args.start,
        end=args.end,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
