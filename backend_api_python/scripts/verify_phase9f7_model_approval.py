#!/usr/bin/env python3
"""Phase 9F-7 验收：Model Lifecycle & Approval。"""

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
        date = f"2024-03-{d+1:02d}"
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
        ModelEvaluationRequest,
        ModelEvaluationService,
    )
    from app.services.research_data.model_evaluation.protocol import ModelEvaluationInject
    from app.services.research_data.model_platform.protocol import ENGINE_VERSION
    from app.services.research_data.model_platform.runner import (
        ModelPlatformError,
        ModelPlatformService,
    )
    from model_platform_golden.golden import (
        create_formal_version,
        golden_model_spec,
        make_model_platform_env,
    )

    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_model_platform@1"
    checks["no_auto_live"] = not hasattr(ModelPlatformService, "auto_live")
    checks["no_promote_strategy"] = not hasattr(
        ModelPlatformService, "promote_strategy"
    )
    checks["has_approve"] = hasattr(ModelPlatformService, "approve_version")
    checks["has_validate"] = hasattr(ModelPlatformService, "validate_version")
    checks["has_revoke"] = hasattr(ModelPlatformService, "revoke_approval")

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9f7_"))
    plat = make_model_platform_env(tmp / "plat")
    model = plat.register_model(golden_model_spec(model_code="verify_approval"))

    # bare APPROVED forbidden
    v0 = create_formal_version(plat, model_id=model.model_id, version="0.9.0")
    plat.transition(v0.model_version_id, "EVALUATING")
    plat.transition(v0.model_version_id, "VALIDATED")
    bare_blocked = False
    try:
        plat.transition(v0.model_version_id, "APPROVED")
    except ModelPlatformError:
        bare_blocked = True
    checks["bare_approved_blocked"] = bare_blocked

    # reject without eval
    _, rej = plat.approve_version(v0.model_version_id, operator="verify", reason="noeval")
    checks["reject_no_eval"] = rej.decision == "REJECTED"
    checks["reject_keeps_lifecycle"] = (
        plat.get_version(v0.model_version_id).lifecycle == "VALIDATED"
    )

    def _run_eval(ver_id: str, sub: str):
        ev = ModelEvaluationService(tmp / sub, model_platform=plat)
        plat.bind_evaluation_service(ev)
        return ev.run_evaluation(
            ModelEvaluationRequest(
                model_version_id=ver_id,
                evaluation_dataset_hash="e" * 64,
                dataset_hash="d" * 64,
                feature_set_hash="f" * 64,
                label_hash="b" * 64,
                evaluation_start="2024-03-01",
                evaluation_end="2024-03-31",
            ),
            inject=ModelEvaluationInject(predictions=_panel()),
        )

    # PASS → approve → activate single ACTIVE
    v17 = create_formal_version(plat, model_id=model.model_id, version="1.7.0")
    r17 = _run_eval(v17.model_version_id, "eval17")
    checks["eval17_pass"] = (
        r17.status == "SUCCEEDED"
        and r17.result is not None
        and r17.result.overall_status == "PASS"
    )
    v17, a17 = plat.approve_version(v17.model_version_id, operator="verify", reason="v17")
    checks["approve17"] = a17.decision == "APPROVED" and v17.lifecycle == "APPROVED"
    act17 = plat.activate(v17.model_version_id, operator="verify", reason="ship17")
    checks["active17"] = act17.lifecycle == "ACTIVE"

    v18 = create_formal_version(plat, model_id=model.model_id, version="1.8.0")
    r18 = _run_eval(v18.model_version_id, "eval18")
    checks["eval18_pass"] = r18.status == "SUCCEEDED"
    v18, a18 = plat.approve_version(v18.model_version_id, operator="verify", reason="v18")
    checks["approve18"] = a18.decision == "APPROVED"
    act18 = plat.activate(v18.model_version_id, operator="verify", reason="ship18")
    checks["active18"] = act18.lifecycle == "ACTIVE"
    old = plat.get_version(v17.model_version_id)
    checks["v17_deprecated"] = (
        old.lifecycle == "DEPRECATED" and old.deprecate_reason_code == "NEW_VERSION"
    )
    actives = [v for v in plat.list_versions(model.model_id) if v.lifecycle == "ACTIVE"]
    checks["single_active"] = len(actives) == 1 and actives[0].model_version_id == (
        v18.model_version_id
    )
    acts = plat.list_activations(model_id=model.model_id)
    checks["has_activation_record"] = any(
        a.to_model_version_id == v18.model_version_id
        and a.from_model_version_id == v17.model_version_id
        for a in acts
    )

    # revoke append-only
    _, rev = plat.revoke_approval(v18.model_version_id, reason="rollback", operator="verify")
    checks["revoke_appended"] = rev.decision == "REVOKED"
    checks["revoke_deprecates"] = (
        plat.get_version(v18.model_version_id).lifecycle == "DEPRECATED"
    )
    approvals = plat.list_approvals(model_version_id=v18.model_version_id)
    checks["old_approved_intact"] = any(
        a.approval_id == a18.approval_id and a.decision == "APPROVED" for a in approvals
    )

    failed = [k for k, ok in checks.items() if not ok]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
