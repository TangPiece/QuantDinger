#!/usr/bin/env python3
"""Phase 2A 验收：Qlib Adapter Core（Runtime / Version / Feature / Processor / Handler）。

用法（在 backend_api_python 下）::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_phase2a_adapter.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def main() -> int:
    try:
        import qlib  # noqa: F401
        from qlib.data import D
    except ImportError:
        print(json.dumps({"ok": False, "error": "pyqlib not installed"}, ensure_ascii=False))
        return 2

    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.ingest.build_golden import build_golden_dataset
    from app.services.research_data.qlib_adapter import (
        ADAPTER_VERSION,
        FeatureAdapter,
        QlibAdapter,
        QlibRuntime,
        UnsupportedFeatureError,
        builtin_cs_zscore_processor,
        builtin_identity_processor,
    )
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
    from app.services.research_data.qlib_materializer.validation import compare_feature_values
    from app.services.research_data.registry import LocalJsonRegistry

    root = Path(tempfile.mkdtemp(prefix="qd_phase2a_"))
    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    start, end = date(2024, 1, 1), date(2024, 6, 30)
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=start,
        end=end,
        universe_version="phase2a.1",
        snapshot_id="snap_phase2a",
        use_fixture=True,
    )
    query = DataQuery(store, registry)
    registry.upsert_processor(builtin_identity_processor())
    registry.upsert_processor(builtin_cs_zscore_processor())

    mat = DefaultQlibMaterializer(query, cache_root=root / "cache", start=start, end=end)
    adapter = QlibAdapter(
        query, materializer=mat, registry=registry, start=start, end=end
    )

    report: dict = {
        "ok": True,
        "adapter_version": ADAPTER_VERSION,
        "dataset_ref": golden["dataset_ref"],
        "checks": {},
    }

    def fail(name: str, detail: dict) -> None:
        report["ok"] = False
        report["checks"][name] = {"ok": False, **detail}

    # 1) Runtime
    try:
        cache = adapter.ensure_cache(golden["dataset_ref"], force=True)
        rt = QlibRuntime()
        rt.activate(cache.cache_path, kernels=1)
        feat = D.features(
            ["sz000001"], ["$close"], start_time="2024-01-01", end_time="2024-06-01"
        )
        if len(feat) <= 0:
            raise RuntimeError("D.features empty after Runtime.activate")
        report["checks"]["runtime"] = {"ok": True, "rows": int(len(feat))}
    except Exception as exc:
        fail("runtime", {"error": str(exc)})

    # 2) VersionResolver
    try:
        b1 = adapter.resolve(golden["dataset_ref"])
        b2 = adapter.resolve(golden["dataset_ref"])
        if b1.bundle_hash != b2.bundle_hash:
            raise RuntimeError("bundle_hash unstable")
        report["checks"]["version"] = {
            "ok": True,
            "dataset_hash": b1.dataset_hash,
            "bundle_hash": b1.bundle_hash,
            "processor_version": b1.processor_version,
        }
    except Exception as exc:
        fail("version", {"error": str(exc)})

    # 3) FeatureAdapter
    try:
        fa = FeatureAdapter()
        exprs = fa.to_qlib_fields(["$close", "Ref($close, 1)", "Mean($close, 5)"])
        try:
            fa.compile_one("Rank($close)")
            raise RuntimeError("Rank should be rejected")
        except UnsupportedFeatureError:
            pass
        report["checks"]["feature"] = {"ok": True, "compiled": exprs}
    except Exception as exc:
        fail("feature", {"error": str(exc)})

    # 4) Processor
    try:
        from app.services.research_data.qlib_adapter import ProcessorAdapter

        pa = ProcessorAdapter(registry)
        learn, infer = pa.build_handler_processors(pa.resolve_definition("cs_zscore@1"))
        if learn != infer or not learn:
            raise RuntimeError("processor learn/infer mismatch or empty")
        report["checks"]["processor"] = {"ok": True, "steps": [x["class"] for x in learn]}
    except Exception as exc:
        fail("processor", {"error": str(exc)})

    # 5) Handler + consistency
    try:
        handler = adapter.build_handler(
            golden["dataset_ref"], start=start, end=end, force_materialize=True
        )
        df = handler.fetch(col_set="feature")
        if df is None or len(df) == 0:
            df = handler.fetch()
        if df is None or len(df) == 0:
            raise RuntimeError("handler.fetch empty")

        ik = "CNStock:000001"
        market = query.market([ik], start, end, price_policy=b1.handle.definition.price_policy)
        qlib_id = to_qlib_instrument(ik).lower()
        feat = D.features(
            [qlib_id],
            ["$close"],
            start_time=str(market["trading_date"].min()),
            end_time=str(market["trading_date"].max()),
        )
        dq_vals = [float(x) for x in market.sort_values("trading_date")["close"].tolist()]
        q_vals = [float(x) for x in feat.iloc[:, 0].tolist()]
        n = min(len(dq_vals), len(q_vals))
        compare_feature_values(dq_vals[:n], q_vals[:n], atol=1e-8, rtol=1e-6)
        report["checks"]["handler"] = {"ok": True, "handler_rows": int(len(df)), "compared": n}
    except Exception as exc:
        fail("handler", {"error": str(exc)})

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
