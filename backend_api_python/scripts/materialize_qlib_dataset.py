#!/usr/bin/env python3
"""将 Dataset（经 DataQuery）物化为本地 Qlib 派生缓存。

用法（在 backend_api_python 下）::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/materialize_qlib_dataset.py \\
      --dataset-ref cn_stock_daily@v1 \\
      --local-root /tmp/qd_canonical --registry-root /tmp/qd_registry
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

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize Dataset to local Qlib cache")
    parser.add_argument("--dataset-ref", default="cn_stock_daily@v1")
    parser.add_argument("--local-root", default=None, help="LocalCanonicalStore root")
    parser.add_argument("--registry-root", default=None, help="LocalJsonRegistry root")
    parser.add_argument(
        "--cache-root",
        default=None,
        help="Parent of qlib-cache/ (default: QD_RESEARCH_CACHE_DIR or ~/.quantdinger/cache)",
    )
    parser.add_argument("--force", action="store_true", help="Ignore READY cache hit")
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete existing materialization cache before build",
    )
    parser.add_argument(
        "--skip-qlib-validate",
        action="store_true",
        help="Skip pyqlib D.features readback (filesystem checks still run inside validate when qlib missing)",
    )
    args = parser.parse_args()

    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.qlib_materializer import cache as cache_mod
    from app.services.research_data.qlib_materializer.identity import compute_materialization_id
    from app.services.research_data.registry import LocalJsonRegistry

    store = LocalCanonicalStore(root=Path(args.local_root) if args.local_root else None)
    if args.registry_root:
        registry = LocalJsonRegistry(root=Path(args.registry_root))
    else:
        registry = LocalJsonRegistry(root=store.root.parent / "registry")

    query = DataQuery(store, registry)
    handle = query.dataset(args.dataset_ref)
    mid = compute_materialization_id(handle.dataset_hash)
    cache_root = Path(args.cache_root) if args.cache_root else None

    if args.wipe:
        cache_mod.invalidate(cache_mod.cache_dir_for(mid, root=cache_root))

    mat = DefaultQlibMaterializer(query, cache_root=cache_root)
    result = mat.materialize(
        args.dataset_ref,
        force=args.force or args.wipe,
        skip_qlib_validate=args.skip_qlib_validate,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
