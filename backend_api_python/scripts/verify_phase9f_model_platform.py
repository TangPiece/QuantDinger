#!/usr/bin/env python3
"""Phase 9F 验收：Model Contract / Lineage / TrainingRun（9F-1～9F-3）。"""

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


def main() -> int:
    from app.services.research_data.model_platform.hashing import compute_model_config_hash
    from app.services.research_data.model_platform.protocol import ENGINE_VERSION
    from app.services.research_data.model_platform.runner import ModelPlatformService
    from model_platform_golden.golden import (
        GOLDEN_CONFIG,
        GOLDEN_MODEL_CODE,
        create_formal_version,
        create_succeeded_run,
        draft_stub_inject,
        formal_inject,
        golden_artifact_spec,
        golden_job_spec,
        golden_model_spec,
        golden_training_run_spec,
        golden_version_spec,
        make_model_platform_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9f_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_model_platform@1"
    svc = make_model_platform_env(tmp / "main")

    checks["no_train"] = not hasattr(ModelPlatformService, "train")
    checks["has_predict"] = hasattr(ModelPlatformService, "predict")  # 9F-4 薄 Predict
    checks["no_evaluate_model"] = not hasattr(ModelPlatformService, "evaluate_model")
    checks["no_auto_live"] = not hasattr(ModelPlatformService, "auto_live")
    checks["has_submit_job"] = hasattr(svc, "submit_training_job")
    checks["has_execute"] = hasattr(svc, "execute_training_run")
    checks["has_retry"] = hasattr(svc, "retry_training_run")

    model = svc.register_model(golden_model_spec())
    bare_reject = False
    try:
        svc.register_version(model.model_id, golden_version_spec())
    except Exception:
        bare_reject = True
    checks["bare_register_rejected"] = bare_reject

    stub = svc.register_version(
        model.model_id,
        golden_version_spec(version="0.0.1-stub"),
        inject=draft_stub_inject(),
    )
    checks["draft_stub_ok"] = stub.lifecycle == "DRAFT"

    version = create_formal_version(svc, model_id=model.model_id, version="1.0.0")
    checks["formal_trained"] = version.lifecycle == "TRAINED"
    checks["formal_has_run_artifact"] = bool(version.training_run_id and version.artifact_id)
    lineage = svc.get_lineage(version.model_version_id)
    checks["lineage_complete"] = all(
        lineage.get(k)
        for k in (
            "dataset_hash",
            "snapshot_id",
            "feature_set_hash",
            "label_hash",
            "training_run_id",
            "artifact_id",
            "repro_manifest_uri",
        )
    )

    # 9F-3 happy path already via create_formal_version; explicit job path
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            requested_version="2.0.0",
            force_new=True,
            idempotency_key="verify-job-2",
        )
    )
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    checks["job_execute_succeeded"] = run.status == "SUCCEEDED" and bool(run.model_version_id)
    checks["job_has_metrics"] = bool(run.metrics_uri and run.logs_uri)

    # prepare fail
    job_miss = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            dataset_hash="",
            requested_version="x.miss",
            force_new=True,
            idempotency_key="verify-miss",
        )
    )
    miss = svc.execute_training_run(job_miss.run_ids[0], inject=formal_inject())
    checks["prepare_fail_no_version"] = (
        miss.status == "FAILED"
        and miss.failure_class == "DATA_MISSING"
        and not miss.model_version_id
    )

    # retry
    job_r = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            requested_version="3.0.0",
            force_new=True,
            idempotency_key="verify-retry",
        )
    )
    failed = svc.execute_training_run(
        job_r.run_ids[0], inject=formal_inject(simulate_fail_at="RUNNING")
    )
    child = svc.retry_training_run(failed.training_run_id)
    ok2 = svc.execute_training_run(child.training_run_id, inject=formal_inject())
    checks["retry_ok"] = (
        failed.status == "FAILED"
        and child.parent_training_run_id == failed.training_run_id
        and ok2.status == "SUCCEEDED"
    )

    term_block = False
    try:
        svc.update_training_run_status(ok2.training_run_id, "FAILED")
    except Exception:
        term_block = True
    checks["terminal_immutable"] = term_block

    queued = svc.create_training_run(
        golden_training_run_spec(model_id=model.model_id, training_run_id="trun_queued")
    )
    non_ok = False
    try:
        svc.create_version_from_run(
            queued.training_run_id,
            version="9.9.9",
            lineage_spec=golden_version_spec(version="9.9.9"),
            artifact_spec=golden_artifact_spec(),
            inject=formal_inject(),
        )
    except Exception:
        non_ok = True
    checks["reject_non_succeeded"] = non_ok

    pkg = ROOT / "app" / "services" / "research_data" / "model_platform"
    clean = True
    for py in pkg.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "from app.services.research_data.model_training" in text:
            clean = False
        if "import qlib" in text or "from qlib" in text:
            clean = False
    checks["no_qlib_trainer_import"] = clean
    checks["model_code"] = model.model_code == GOLDEN_MODEL_CODE
    checks["config_hash_api"] = bool(compute_model_config_hash(GOLDEN_CONFIG))

    mig = (
        ROOT.parent
        / "workers"
        / "qd-research-d1"
        / "migrations"
        / "0039_model_platform.sql"
    )
    checks["d1_0039_exists"] = mig.is_file()

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
