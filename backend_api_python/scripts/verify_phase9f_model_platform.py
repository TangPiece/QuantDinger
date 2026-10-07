#!/usr/bin/env python3
"""Phase 9F 验收：Model Contract & Lineage（含 9F-2）。"""

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
    checks["no_predict"] = not hasattr(ModelPlatformService, "predict")
    checks["no_evaluate_model"] = not hasattr(ModelPlatformService, "evaluate_model")
    checks["no_auto_live"] = not hasattr(ModelPlatformService, "auto_live")
    checks["no_promote_strategy"] = not hasattr(ModelPlatformService, "promote_strategy")
    checks["has_create_from_run"] = hasattr(svc, "create_version_from_run")
    checks["has_get_lineage"] = hasattr(svc, "get_lineage")
    checks["has_get_active"] = hasattr(svc, "get_active_version")

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
            "processor_version",
            "training_run_id",
            "artifact_id",
            "repro_manifest_uri",
        )
    )
    repro = svc.get_repro_manifest(version.model_version_id)
    checks["repro_manifest"] = bool(repro.get("artifact_checksum") and repro.get("version_content_hash"))

    h1 = compute_model_config_hash(GOLDEN_CONFIG)
    checks["config_hash_stable"] = h1 == version.model_config_hash

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

    run_ok = create_succeeded_run(svc, model_id=model.model_id, training_run_id="trun_badcs")
    bad_cs = False
    try:
        svc.create_version_from_run(
            run_ok.training_run_id,
            version="8.8.8",
            lineage_spec=golden_version_spec(version="8.8.8"),
            artifact_spec=golden_artifact_spec(checksum="nope"),
            inject=formal_inject(),
        )
    except Exception:
        bad_cs = True
    checks["reject_bad_checksum"] = bad_cs

    del_ok = False
    try:
        svc.delete_version(version.model_version_id)
    except Exception:
        del_ok = True
    checks["delete_forbidden"] = del_ok

    rebind = False
    try:
        svc.register_artifact(golden_artifact_spec(version.model_version_id))
    except Exception:
        rebind = True
    checks["artifact_rebind_forbidden"] = rebind

    for target in ("EVALUATING", "VALIDATED", "APPROVED"):
        version = svc.transition(version.model_version_id, target)  # type: ignore[arg-type]
    active = svc.activate(version.model_version_id)
    checks["active_query"] = (
        svc.get_active_version(model.model_id).model_version_id == active.model_version_id
    )
    svc.retire(active.model_version_id)
    no_active = False
    try:
        svc.get_active_version(model.model_id)
    except Exception:
        no_active = True
    checks["no_active_after_retire"] = no_active
    checks["model_code"] = model.model_code == GOLDEN_MODEL_CODE

    mig = (
        ROOT.parent
        / "workers"
        / "qd-research-d1"
        / "migrations"
        / "0039_model_platform.sql"
    )
    checks["d1_0039_exists"] = mig.is_file() and "training_run" in mig.read_text(
        encoding="utf-8"
    )

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
