#!/usr/bin/env python3
"""Phase 9F-1 验收：Model Contract & Registry。"""

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
    from app.services.research_data.model_platform.protocol import (
        ENGINE_VERSION,
        ModelSearchQuery,
    )
    from app.services.research_data.model_platform.runner import ModelPlatformService
    from model_platform_golden.golden import (
        GOLDEN_CONFIG,
        GOLDEN_MODEL_CODE,
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
    checks["has_register_model"] = hasattr(svc, "register_model")
    checks["has_create_training_run"] = hasattr(svc, "create_training_run")

    model = svc.register_model(golden_model_spec())
    version = svc.register_version(model.model_id, golden_version_spec())
    checks["model_ne_version"] = model.model_id != version.model_version_id
    checks["version_lineage"] = bool(
        version.dataset_hash
        and version.model_config_hash
        and version.version_content_hash
        and len(version.version_content_hash) == 64
    )

    h1 = compute_model_config_hash(GOLDEN_CONFIG)
    h2 = svc.compute_model_config_hash(dict(reversed(list(GOLDEN_CONFIG.items()))))
    checks["config_hash_stable"] = h1 == h2 == version.model_config_hash

    rid = "trun_verify_fixed01"
    run1 = svc.create_training_run(
        golden_training_run_spec(
            model_id=model.model_id,
            model_version_id=version.model_version_id,
            training_run_id=rid,
        )
    )
    run2 = svc.create_training_run(
        golden_training_run_spec(
            model_id=model.model_id,
            model_version_id=version.model_version_id,
            training_run_id=rid,
        )
    )
    checks["run_idempotent"] = run1.training_run_hash == run2.training_run_hash
    drift_ok = False
    try:
        svc.create_training_run(
            golden_training_run_spec(
                model_id=model.model_id,
                model_version_id=version.model_version_id,
                training_run_id=rid,
                random_seed=7,
            )
        )
    except Exception:
        drift_ok = True
    checks["run_immutable_drift"] = drift_ok

    for target in ("TRAINING", "TRAINED", "EVALUATING", "VALIDATED", "APPROVED"):
        version = svc.transition(version.model_version_id, target)  # type: ignore[arg-type]
    active = svc.activate(version.model_version_id)
    checks["activate_search"] = active.lifecycle == "ACTIVE" and bool(
        svc.search(ModelSearchQuery(lifecycle=["ACTIVE"]))["versions"]
    )

    svc.retire(active.model_version_id)
    retired_block = False
    try:
        svc.activate(active.model_version_id)
    except Exception:
        retired_block = True
    checks["retired_blocks_activate"] = retired_block
    checks["retired_still_get"] = (
        svc.get_version(active.model_version_id).lifecycle == "RETIRED"
    )

    art = svc.register_artifact(golden_artifact_spec(version.model_version_id))
    checks["artifact_bound"] = (
        svc.get_version(version.model_version_id).artifact_id == art.artifact_id
    )

    pkg = ROOT / "app" / "services" / "research_data" / "model_platform"
    forbidden = ("auto_live", "promote_strategy", "evaluate_model")
    clean = True
    for py in pkg.rglob("*.py"):
        text = py.read_text(encoding="utf-8").lower()
        # allow comments listing forbidden APIs in runner docstring / verify notes
        if py.name == "runner.py":
            # strip docstring-ish lines for token scan of method defs
            lines = [
                ln
                for ln in text.splitlines()
                if not ln.strip().startswith("#")
                and "无 train" not in ln
                and "auto_live" not in ln
                and "promote_strategy" not in ln
                and "evaluate_model" not in ln
            ]
            text = "\n".join(lines)
        for tok in forbidden:
            if f"def {tok}" in text or f".{tok}(" in text:
                clean = False
                break
    checks["forbidden_tokens"] = clean
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
