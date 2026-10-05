#!/usr/bin/env python3
"""Phase 2B 验收：Dataset / Handler / segments / label / cache。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_phase2b_dataset.py
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
        FeatureAdapter,
        LabelAdapter,
        QlibAdapter,
        ResearchDatasetSpec,
        SegmentRange,
        SegmentSpec,
        UnsupportedFeatureError,
    )
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
    from app.services.research_data.qlib_materializer.validation import compare_feature_values
    from app.services.research_data.registry import LocalJsonRegistry

    root = Path(tempfile.mkdtemp(prefix="qd_phase2b_"))
    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    start, end = date(2024, 1, 1), date(2024, 6, 30)
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=start,
        end=end,
        universe_version="phase2b.1",
        snapshot_id="snap_phase2b",
        use_fixture=True,
    )
    query = DataQuery(store, registry)
    mat = DefaultQlibMaterializer(query, cache_root=root / "cache", start=start, end=end)
    adapter = QlibAdapter(
        query,
        materializer=mat,
        registry=registry,
        dataset_cache_root=root / "qlib-dataset-cache",
        start=start,
        end=end,
    )
    spec = ResearchDatasetSpec(
        dataset_ref=golden["dataset_ref"],
        segments=SegmentSpec(
            train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
            valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
            test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
        ),
    )

    report: dict = {"ok": True, "dataset_ref": golden["dataset_ref"], "checks": {}}

    def fail(name: str, detail: dict) -> None:
        report["ok"] = False
        report["checks"][name] = {"ok": False, **detail}

    # segments
    try:
        segs = spec.segments.to_qlib_segments()
        assert list(segs.keys()) == ["train", "valid", "test"]
        report["checks"]["segments"] = {"ok": True, "segments": segs}
    except Exception as exc:
        fail("segments", {"error": str(exc)})

    # label vs feature isolation
    try:
        la = LabelAdapter()
        _, compiled = la.resolve(None)
        fa = FeatureAdapter()
        try:
            fa.compile_one(compiled.qlib_expression)
            raise RuntimeError("feature must reject label expression")
        except UnsupportedFeatureError:
            pass
        report["checks"]["label_isolation"] = {
            "ok": True,
            "label": compiled.qlib_expression,
            "horizon": compiled.horizon,
        }
    except Exception as exc:
        fail("label_isolation", {"error": str(exc)})

    # handler + dataset
    try:
        qd = adapter.build_qd_handler(spec, force_materialize=True)
        feat = qd.fetch(col_set="feature")
        lab = qd.fetch(col_set="label")
        if feat is None or len(feat) == 0:
            raise RuntimeError("feature fetch empty")
        if lab is None or len(lab) == 0:
            raise RuntimeError("label fetch empty")
        ds = adapter.build_dataset(spec)
        ds2 = adapter.build_dataset(spec)
        report["checks"]["handler_dataset"] = {
            "ok": True,
            "feature_rows": int(len(feat)),
            "label_rows": int(len(lab)),
            "dataset_hash": ds.qd_dataset_hash,  # type: ignore[attr-defined]
            "artifact_id": ds.qd_artifact_id,  # type: ignore[attr-defined]
            "cache_hit_second": bool(ds2.qd_cache_hit),  # type: ignore[attr-defined]
            "instruments": qd.instruments,
        }
    except Exception as exc:
        fail("handler_dataset", {"error": str(exc)})

    # consistency
    try:
        ik = "CNStock:000001"
        market = query.market([ik], start, end)
        qid = to_qlib_instrument(ik).lower()
        close = D.features(
            [qid],
            ["$close"],
            start_time=str(market["trading_date"].min()),
            end_time=str(market["trading_date"].max()),
        )
        dq_vals = [float(x) for x in market.sort_values("trading_date")["close"].tolist()]
        q_vals = [float(x) for x in close.iloc[:, 0].tolist()]
        n = min(len(dq_vals), len(q_vals))
        compare_feature_values(dq_vals[:n], q_vals[:n], atol=1e-8, rtol=1e-6)
        report["checks"]["consistency"] = {"ok": True, "compared": n}
    except Exception as exc:
        fail("consistency", {"error": str(exc)})

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
