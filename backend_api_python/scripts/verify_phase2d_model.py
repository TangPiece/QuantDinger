#!/usr/bin/env python3
"""Phase 2D 验收：LightGBM 训练 / predict / artifact / 追溯。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_phase2d_model.py
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


def _check_lightgbm() -> bool:
    from app.services.research_data.model_training.adapter import lightgbm_runtime_available

    return lightgbm_runtime_available()


def main() -> int:
    try:
        import qlib  # noqa: F401
    except ImportError:
        print(json.dumps({"ok": False, "error": "pyqlib not installed"}, ensure_ascii=False))
        return 2

    if not _check_lightgbm():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "lightgbm unavailable (macOS: brew install libomp)",
                },
                ensure_ascii=False,
            )
        )
        return 2

    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.contracts import DatasetDefinition
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.ingest.build_golden import (
        GOLDEN_DATASET_CODE,
        build_golden_dataset,
    )
    from app.services.research_data.model_training import (
        ModelArtifactStore,
        ModelTrainSpec,
        ModelTrainer,
        builtin_lgb_baseline_model,
    )
    from app.services.research_data.qlib_adapter import (
        QlibAdapter,
        ResearchDatasetSpec,
        SegmentRange,
        SegmentSpec,
        builtin_qd_standard_processor,
    )
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.registry import LocalJsonRegistry

    root = Path(tempfile.mkdtemp(prefix="qd_phase2d_"))
    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    start, end = date(2024, 1, 1), date(2024, 6, 30)
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=start,
        end=end,
        universe_version="phase2d.1",
        snapshot_id="snap_phase2d",
        use_fixture=True,
    )
    query = DataQuery(store, registry)
    registry.upsert_processor(builtin_qd_standard_processor())
    registry.upsert_model(builtin_lgb_baseline_model())

    handle = query.dataset(golden["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_2d",
        name="phase2d verify",
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
    dataset_ref = f"{GOLDEN_DATASET_CODE}@v1_2d"

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
    spec = ModelTrainSpec(
        dataset_spec=ResearchDatasetSpec(dataset_ref=dataset_ref, segments=segments),
        model=builtin_lgb_baseline_model(),
        seed=42,
    )
    artifact_store = ModelArtifactStore(root=root / "artifact_root")
    trainer = ModelTrainer(adapter, registry, artifact_store=artifact_store)

    report: dict = {"ok": True, "checks": {}}
    try:
        result = trainer.train(spec)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    report["checks"]["train"] = {
        "ok": True,
        "artifact_id": result.artifact_id,
        "predictions": len(result.predictions),
        "valid_mse": result.metrics.get("valid_mse"),
    }
    report["checks"]["traceability"] = {
        "ok": all(
            p.dataset_hash == result.dataset_hash and p.bundle_hash == result.bundle_hash
            for p in result.predictions
        ),
    }
    meta = artifact_store.read_metadata(result.artifact_id)
    report["checks"]["metadata"] = {
        "ok": meta.get("dataset_hash") == result.dataset_hash
        and meta.get("fit_end", meta.get("segments", {})) is not None,
        "processor_version": meta.get("processor_version"),
    }
    if not report["checks"]["traceability"]["ok"]:
        report["ok"] = False

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
