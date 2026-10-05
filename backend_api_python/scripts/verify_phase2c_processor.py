#!/usr/bin/env python3
"""Phase 2C 验收：Processor Pipeline（白名单 / fit / hash / fetch）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_phase2c_processor.py
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
    except ImportError:
        print(json.dumps({"ok": False, "error": "pyqlib not installed"}, ensure_ascii=False))
        return 2

    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.contracts import DatasetDefinition
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.ingest.build_golden import (
        GOLDEN_DATASET_CODE,
        build_golden_dataset,
    )
    from app.services.research_data.qlib_adapter import (
        ADAPTER_VERSION,
        ProcessorAdapter,
        QlibAdapter,
        ResearchDatasetSpec,
        SegmentRange,
        SegmentSpec,
        VersionResolver,
        builtin_cs_zscore_processor,
        builtin_qd_standard_processor,
        inject_fit_window,
    )
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.registry import (
        LocalJsonRegistry,
        ProcessorImmutabilityError,
    )

    root = Path(tempfile.mkdtemp(prefix="qd_phase2c_"))
    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    start, end = date(2024, 1, 1), date(2024, 6, 30)
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=start,
        end=end,
        universe_version="phase2c.1",
        snapshot_id="snap_phase2c",
        use_fixture=True,
    )
    query = DataQuery(store, registry)
    registry.upsert_processor(builtin_cs_zscore_processor())
    registry.upsert_processor(builtin_qd_standard_processor())

    report: dict = {
        "ok": True,
        "adapter_version": ADAPTER_VERSION,
        "checks": {},
    }

    # --- 白名单编译 ---
    pa = ProcessorAdapter(registry)
    std = registry.get_processor("qd_standard@1")
    learn, infer = pa.build_handler_processors(std)
    assert learn == infer
    assert [s["class"] for s in learn] == [
        "Fillna",
        "RobustZScoreNorm",
        "CSZScoreNorm",
    ]
    report["checks"]["whitelist"] = {"ok": True, "classes": [s["class"] for s in learn]}

    # --- immutability ---
    try:
        registry.upsert_processor(
            type(std)(code="qd_standard", version="1", pipeline=[{"class": "Fillna"}])
        )
        report["ok"] = False
        report["checks"]["immutability"] = {"ok": False, "error": "expected reject"}
    except ProcessorImmutabilityError:
        report["checks"]["immutability"] = {"ok": True}

    # --- 挂载 qd_standard 到 dataset ---
    handle = query.dataset(golden["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_2c",
        name="phase2c standard",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=base.price_policy,
        processor="qd_standard@1",
        pit=True,
    )
    registry.upsert_dataset(definition, status="validated")
    ref = f"{GOLDEN_DATASET_CODE}@v1_2c"

    mat = DefaultQlibMaterializer(query, cache_root=root / "cache", start=start, end=end)
    adapter = QlibAdapter(
        query,
        materializer=mat,
        registry=registry,
        dataset_cache_root=root / "qlib-dataset-cache",
        start=start,
        end=end,
    )
    segments = SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )
    spec = ResearchDatasetSpec(dataset_ref=ref, segments=segments)
    assert spec.resolved_fit_end() < segments.valid.start

    bundle = VersionResolver(query, registry).resolve(ref)
    report["checks"]["hash"] = {
        "ok": True,
        "dataset_hash": bundle.dataset_hash,
        "bundle_hash": bundle.bundle_hash,
        "pipeline_digest": bundle.pipeline_digest,
        "processor_version": bundle.processor_version,
    }

    # --- fit 注入 ---
    injected = inject_fit_window(
        learn,
        spec.resolved_fit_start().isoformat(),
        spec.resolved_fit_end().isoformat(),
    )
    robust = next(s for s in injected if s["class"] == "RobustZScoreNorm")
    assert robust["kwargs"]["fit_end_time"] == "2024-02-29"
    fillna = next(s for s in injected if s["class"] == "Fillna")
    assert "fit_start_time" not in fillna["kwargs"]
    report["checks"]["fit_isolation"] = {
        "ok": True,
        "fit_start": "2024-01-01",
        "fit_end": "2024-02-29",
        "fit_end_lt_valid": True,
    }

    # --- handler fetch ---
    qd = adapter.build_qd_handler(spec, force_materialize=True)
    feat = qd.fetch(col_set="feature")
    rows = int(len(feat)) if feat is not None else 0
    if rows <= 0:
        report["ok"] = False
        report["checks"]["fetch"] = {"ok": False, "rows": rows}
    else:
        report["checks"]["fetch"] = {"ok": True, "rows": rows}

    ds1 = adapter.build_dataset(spec)
    ds2 = adapter.build_dataset(spec)
    report["checks"]["reproducible"] = {
        "ok": bool(ds2.qd_cache_hit) and ds1.qd_bundle_hash == ds2.qd_bundle_hash,  # type: ignore
        "cache_hit_second": bool(ds2.qd_cache_hit),  # type: ignore
    }
    if not report["checks"]["reproducible"]["ok"]:
        report["ok"] = False

    # cs_zscore vs qd_standard → hash 不同
    definition_cs = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_2c_cs",
        name="cs only",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=base.price_policy,
        processor="cs_zscore@1",
        pit=True,
    )
    registry.upsert_dataset(definition_cs, status="validated")
    b_cs = VersionResolver(query, registry).resolve(f"{GOLDEN_DATASET_CODE}@v1_2c_cs")
    report["checks"]["processor_hash_delta"] = {
        "ok": b_cs.bundle_hash != bundle.bundle_hash
        and b_cs.dataset_hash != bundle.dataset_hash,
        "cs_bundle": b_cs.bundle_hash[:16],
        "std_bundle": bundle.bundle_hash[:16],
    }
    if not report["checks"]["processor_hash_delta"]["ok"]:
        report["ok"] = False

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
