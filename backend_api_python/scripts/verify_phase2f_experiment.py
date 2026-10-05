#!/usr/bin/env python3
"""Phase 2F 验收：Experiment 编排 / manifest / 双跑复现。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_phase2f_experiment.py
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

    from app.services.research_data.model_training.adapter import lightgbm_runtime_available

    if not lightgbm_runtime_available():
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
    from app.services.research_data.experiment import (
        ExperimentManifestStore,
        ExperimentRunner,
        ExperimentSpec,
        is_reproducible,
    )
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
        VersionResolver,
        builtin_qd_standard_processor,
    )
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.registry import LocalJsonRegistry
    from app.services.research_data.signal import (
        EqualWeightPortfolio,
        SignalPipeline,
        SignalRunSpec,
        TopKStrategy,
    )
    from app.services.research_data.signal.artifact_store import SignalArtifactStore

    root = Path(tempfile.mkdtemp(prefix="qd_phase2f_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(root / "cache")
    os.environ["MLFLOW_TRACKING_URI"] = f"file:{root / 'mlruns'}"

    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    start, end = date(2024, 1, 1), date(2024, 6, 30)
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=start,
        end=end,
        universe_version="2024.06",
        snapshot_id="snap_phase2f_verify",
        use_fixture=True,
        status="validated",
    )
    query = DataQuery(store, registry)
    materializer = DefaultQlibMaterializer(
        query, cache_root=root / "qlib_cache", start=start, end=end
    )
    registry.upsert_processor(builtin_qd_standard_processor())
    registry.upsert_model(builtin_lgb_baseline_model())

    handle = query.dataset(golden["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_2f_verify",
        name="phase2f verify",
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
    dataset_ref = f"{GOLDEN_DATASET_CODE}@v1_2f_verify"

    adapter = QlibAdapter(
        query,
        materializer=materializer,
        registry=registry,
        dataset_cache_root=root / "ds_cache",
        start=start,
        end=end,
    )
    trainer = ModelTrainer(
        adapter, registry, artifact_store=ModelArtifactStore(root=root / "model_art")
    )
    signals = SignalPipeline(
        registry, artifact_store=SignalArtifactStore(root=root / "signal_art")
    )
    manifest_store = ExperimentManifestStore(root=root / "exp_art")
    runner = ExperimentRunner(
        adapter,
        registry,
        model_trainer=trainer,
        signal_pipeline=signals,
        manifest_store=manifest_store,
    )

    segments = SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )
    spec = ExperimentSpec(
        name="phase2f_verify",
        train=ModelTrainSpec(
            dataset_spec=ResearchDatasetSpec(dataset_ref=dataset_ref, segments=segments),
            model=builtin_lgb_baseline_model(),
            seed=42,
        ),
        signal=SignalRunSpec(
            strategy=TopKStrategy(k=2),
            portfolio=EqualWeightPortfolio(),
        ),
    )

    a = runner.run(spec)
    exp_after_a = registry.get_experiment(a.experiment_id)
    b = runner.run(spec)
    man = manifest_store.read(a.experiment_id)
    bundle = VersionResolver(query, registry).resolve(dataset_ref)
    exp = registry.get_experiment(a.experiment_id)

    checks = {
        "create": {
            "ok": bool(a.experiment_id and a.model_artifact_id and a.signal_artifact_id),
            "experiment_id": a.experiment_id,
        },
        "mlflow": {
            # 同 experiment_id 第二次运行会刷新 mlflow_run_id；以首次登记为准
            "ok": bool(a.mlflow_run_id)
            and exp_after_a.mlflow_run_id == a.mlflow_run_id
            and bool(b.mlflow_run_id),
            "mlflow_run_id": a.mlflow_run_id,
        },
        "dataset_hash": {
            "ok": man.dataset_hash == bundle.dataset_hash == a.dataset_hash,
        },
        "artifacts": {
            "ok": bool(
                registry.get_artifact(a.model_artifact_id).checksum
                and registry.get_artifact(a.signal_artifact_id).checksum
            ),
        },
        "manifest": {
            "ok": man.experiment_id == a.experiment_id,
            "uri": a.manifest_uri,
        },
        "reproducible": {
            "ok": is_reproducible(a, b) and a.experiment_id == b.experiment_id,
        },
        "metrics": {
            "ok": "valid_mse" in a.metrics and "long_count" in a.metrics,
            "keys": sorted(a.metrics.keys()),
        },
        "registry": {
            "ok": exp.experiment_id == a.experiment_id and bool(exp.repro_fingerprint),
        },
    }
    ok = all(bool(c.get("ok")) for c in checks.values())
    print(
        json.dumps(
            {"ok": ok, "checks": checks, "root": str(root)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
