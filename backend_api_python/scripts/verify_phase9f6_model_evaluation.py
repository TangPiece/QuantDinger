#!/usr/bin/env python3
"""Phase 9F-6 验收：Model Evaluation。"""

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


def _panel():
    rows = []
    for d in range(6):
        date = f"2024-02-{d+1:02d}"
        for i in range(10):
            label = float(i)
            rows.append(
                {
                    "date": date,
                    "instrument": f"CNStock:{i:06d}",
                    "prediction": label * 0.2 + i,
                    "label": label,
                }
            )
    return rows


def main() -> int:
    from app.services.research_data.model_evaluation import (
        ENGINE_VERSION,
        ModelEvaluationRequest,
        ModelEvaluationService,
    )
    from app.services.research_data.model_evaluation.protocol import ModelEvaluationInject
    from app.services.research_data.model_platform.runner import ModelPlatformService
    from model_platform_golden.golden import (
        create_formal_version,
        golden_model_spec,
        make_model_platform_env,
    )

    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_model_evaluation@1"
    checks["no_evaluate_model"] = not hasattr(ModelPlatformService, "evaluate_model")
    checks["no_auto_live"] = not hasattr(ModelEvaluationService, "auto_live")

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9f6_"))
    plat = make_model_platform_env(tmp / "plat")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    svc = ModelEvaluationService(tmp / "eval", model_platform=plat)

    inj = ModelEvaluationInject(predictions=_panel())
    req = ModelEvaluationRequest(
        model_version_id=ver.model_version_id,
        evaluation_dataset_hash="e" * 64,
        dataset_hash="d" * 64,
        feature_set_hash="f" * 64,
        label_hash="b" * 64,
        evaluation_start="2024-02-01",
        evaluation_end="2024-02-28",
    )
    run = svc.run_evaluation(req, inject=inj)
    checks["succeeded"] = run.status == "SUCCEEDED"
    checks["has_ic"] = run.result is not None and run.result.raw_metrics.get(
        "predictive", {}
    ).get("mean_ic") is not None
    checks["has_rank_ic"] = run.result is not None and run.result.raw_metrics.get(
        "predictive", {}
    ).get("mean_rank_ic") is not None
    art = svc.get_artifact_dir(run.evaluation_run_id)
    checks["artifact"] = (art / "metrics.json").is_file() and (
        art / "manifest.json"
    ).is_file()

    run2 = svc.run_evaluation(
        ModelEvaluationRequest(
            model_version_id=ver.model_version_id,
            evaluation_dataset_hash="e" * 64,
            feature_set_hash="f" * 64,
            label_hash="b" * 64,
            evaluation_start="2024-03-01",
            evaluation_end="2024-03-31",
        ),
        inject=inj,
    )
    checks["two_runs"] = run.evaluation_run_id != run2.evaluation_run_id

    blocked = svc.run_evaluation(
        req.model_copy(update={"evaluation_start": "2025-01-01", "evaluation_end": "2025-01-31"}),
        inject=ModelEvaluationInject(predictions=_panel(), force_pit_fail=True),
    )
    checks["pit_blocked"] = blocked.status == "BLOCKED"

    idem = svc.run_evaluation(req, inject=inj)
    checks["idempotent"] = idem.evaluation_run_id == run.evaluation_run_id

    # 不把 IC 写进 ModelVersion
    ver2 = plat.get_version(ver.model_version_id)
    checks["version_no_ic_field"] = not hasattr(ver2, "mean_ic") and ver2.lifecycle in (
        "TRAINED",
        "EVALUATING",
        "VALIDATED",
        "APPROVED",
        "ACTIVE",
    )

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
