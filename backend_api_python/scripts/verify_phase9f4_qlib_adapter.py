#!/usr/bin/env python3
"""Phase 9F-4 验收：Model Adapter Contract +（可选）Qlib 真实训练。

无 qlib/lightgbm runtime 时仍验合同 / registry / stub；真实训 skip。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def _runtime_ok() -> bool:
    try:
        import qlib  # noqa: F401
    except ImportError:
        return False
    from app.services.research_data.model_adapters import lightgbm_runtime_available

    return lightgbm_runtime_available()


def main() -> int:
    from app.services.research_data.model_adapters import (
        ADAPTER_ENGINE_VERSION,
        default_adapter_registry,
        map_training_config_to_lgb,
    )
    from app.services.research_data.model_platform.protocol import ENGINE_VERSION
    from app.services.research_data.model_platform.runner import ModelPlatformService
    from model_platform_golden.golden import (
        formal_inject,
        golden_job_spec,
        golden_model_spec,
        make_model_platform_env,
    )

    checks: dict[str, object] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_model_platform@1"
    checks["adapter_version"] = ADAPTER_ENGINE_VERSION == "qd_model_adapter@1"
    checks["registry_has_lgb"] = "LIGHTGBM" in default_adapter_registry().keys()
    checks["has_predict"] = hasattr(ModelPlatformService, "predict")
    checks["config_map"] = bool(
        map_training_config_to_lgb({"parameters": {"num_leaves": 8}}, seed=1)
    )

    pkg = ROOT / "app" / "services" / "research_data" / "model_platform"
    clean = True
    for py in pkg.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "from app.services.research_data.model_training" in text:
            clean = False
        if "import qlib" in text or "from qlib" in text:
            clean = False
    checks["model_platform_no_qlib_import"] = clean

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9f4_"))
    svc = make_model_platform_env(tmp / "stub")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            resource_config={"executor": "stub"},
            force_new=True,
            idempotency_key="verify-stub",
        )
    )
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    checks["stub_succeeded"] = run.status == "SUCCEEDED" and bool(run.model_version_id)

    job_fail = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            requested_version="9.0.0",
            resource_config={"executor": "qlib"},
            dataset_ref="",
            force_new=True,
            idempotency_key="verify-qlib-noref",
        )
    )
    failed = svc.execute_training_run(
        job_fail.run_ids[0],
        inject=formal_inject(skip_dataset_ref_check=True),
    )
    checks["qlib_missing_ref_failed"] = failed.status == "FAILED" and not failed.model_version_id

    checks["qlib_runtime"] = _runtime_ok()
    checks["qlib_train"] = {"skipped": True}
    if checks["qlib_runtime"]:
        try:
            from datetime import date

            from app.services.research_data.canonical_store import LocalCanonicalStore
            from app.services.research_data.contracts import DatasetDefinition
            from app.services.research_data.data_query import DataQuery
            from app.services.research_data.ingest.build_golden import (
                GOLDEN_DATASET_CODE,
                build_golden_dataset,
            )
            from app.services.research_data.model_training import (
                ModelArtifactStore as TrainStore,
                builtin_lgb_baseline_model,
            )
            from app.services.research_data.qlib_adapter import (
                QlibAdapter,
                builtin_qd_standard_processor,
            )
            from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
            from app.services.research_data.registry import LocalJsonRegistry

            root = tmp / "qlib_live"
            store = LocalCanonicalStore(root=root / "canonical")
            registry = LocalJsonRegistry(root=root / "registry")
            start, end = date(2024, 1, 1), date(2024, 6, 30)
            golden = build_golden_dataset(
                store,
                registry,
                instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
                start=start,
                end=end,
                universe_version="phase9f4.1",
                snapshot_id="snap_phase9f4",
                use_fixture=True,
            )
            query = DataQuery(store, registry)
            registry.upsert_processor(builtin_qd_standard_processor())
            registry.upsert_model(builtin_lgb_baseline_model())
            handle = query.dataset(golden["dataset_ref"])
            base = handle.definition
            definition = DatasetDefinition(
                code=GOLDEN_DATASET_CODE,
                version="v1_9f4",
                name="phase9f4 verify",
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
            dataset_ref = f"{GOLDEN_DATASET_CODE}@v1_9f4"
            handle2 = query.dataset(dataset_ref)

            mat = DefaultQlibMaterializer(
                query, cache_root=root / "cache", start=start, end=end
            )
            adapter = QlibAdapter(
                query,
                materializer=mat,
                registry=registry,
                dataset_cache_root=root / "qlib-dataset-cache",
                start=start,
                end=end,
            )
            train_store = TrainStore(root=root / "artifact_root")
            plat = ModelPlatformService(
                root / "model_platform",
                data_query=query,
                qlib_adapter=adapter,
                research_registry=registry,
                train_artifact_store=train_store,
            )
            m = plat.register_model(golden_model_spec(model_code="alpha_lgb_9f4"))
            j = plat.submit_training_job(
                golden_job_spec(
                    model_id=m.model_id,
                    model_code="alpha_lgb_9f4",
                    requested_version="1.0.0",
                    dataset_ref=dataset_ref,
                    dataset_hash=handle2.dataset_hash,
                    snapshot_id=handle2.definition.snapshot_id or "snap_phase9f4",
                    processor_version="qd_standard@1",
                    resource_config={"executor": "qlib", "cpu": 1},
                    train_start="2024-01-01",
                    train_end="2024-02-29",
                    validation_start="2024-03-01",
                    validation_end="2024-04-30",
                    metadata={"test_start": "2024-05-01", "test_end": "2024-06-30"},
                    training_config={
                        "algorithm": "lightgbm",
                        "objective": "regression",
                        "parameters": {"learning_rate": 0.05, "num_leaves": 8},
                        "num_boost_round": 8,
                        "early_stopping": {"rounds": 3},
                    },
                    force_new=True,
                    idempotency_key="verify-qlib-live",
                )
            )
            inj = formal_inject(
                known_hashes={
                    "dataset_hash": handle2.dataset_hash,
                    "feature_set_hash": "f" * 64,
                    "label_hash": "b" * 64,
                    "snapshot_id": handle2.definition.snapshot_id or "snap_phase9f4",
                },
                skip_dataset_ref_check=False,
            )
            # feature/label hashes from golden_job still apply
            live = plat.execute_training_run(j.run_ids[0], inject=inj)
            checks["qlib_train"] = {
                "skipped": False,
                "status": live.status,
                "has_version": bool(live.model_version_id),
                "failure": live.failure_reason,
                "metrics": bool(live.metrics),
            }
            checks["qlib_train_ok"] = live.status == "SUCCEEDED" and bool(
                live.model_version_id
            )
        except Exception as exc:
            checks["qlib_train"] = {"skipped": False, "error": str(exc)}
            checks["qlib_train_ok"] = False
    else:
        checks["qlib_train_ok"] = True  # skip 不算失败

    bool_keys = [
        "engine_version",
        "adapter_version",
        "registry_has_lgb",
        "has_predict",
        "config_map",
        "model_platform_no_qlib_import",
        "stub_succeeded",
        "qlib_missing_ref_failed",
        "qlib_train_ok",
    ]
    ok = all(bool(checks[k]) for k in bool_keys)
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
