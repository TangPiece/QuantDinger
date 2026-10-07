#!/usr/bin/env python3
"""Phase 9C 验收：Factor Evaluation Platform。"""

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
    from app.services.research_data.evaluation_platform.protocol import ENGINE_VERSION
    from app.services.research_data.evaluation_platform.runner import (
        FactorEvaluationPlatformService,
    )
    from evaluation_platform_golden.golden import (
        GOLDEN_DATASET_REF,
        GOLDEN_FACTOR_REF,
        GOLDEN_POLICY_ALT_ID,
        GOLDEN_POLICY_ID,
        evaluation_inject,
        make_evaluation_platform_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9c_"))
    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_evaluation_platform@1"

    svc, ds, _reg, days, window = make_evaluation_platform_env(tmp / "main")
    inj = evaluation_inject(days=days)
    checks["no_mine_api"] = not hasattr(FactorEvaluationPlatformService, "mine_factors")
    checks["no_promote_api"] = not hasattr(FactorEvaluationPlatformService, "promote")
    checks["no_capacity_curve"] = not hasattr(
        FactorEvaluationPlatformService, "capacity_curve"
    )

    blocked = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=evaluation_inject(gate_blocked=True, days=days),
    )
    checks["gate_blocked_status"] = blocked.status == "BLOCKED"
    checks["gate_no_ic_hash"] = not blocked.metric_hash

    ok_run = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=inj,
    )
    checks["success_pointers"] = bool(
        ok_run.evaluation_hash
        and ok_run.metric_hash
        and ok_run.group_evaluation_hash
        and ok_run.stability_hash
    )
    checks["pins_dataset"] = ok_run.dataset_hash == ds.get(GOLDEN_DATASET_REF).dataset_hash
    score = svc.get_quality_score(ok_run.evaluation_id)
    checks["quality_score_and_raw"] = bool(
        score.total_score >= 0 and score.raw_metrics.get("ic_by_horizon")
    )

    idem = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=inj,
    )
    checks["idempotent"] = idem.evaluation_id == ok_run.evaluation_id

    alt = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ALT_ID,
        window=window,
        inject=inj,
    )
    checks["policy_change_new_run"] = alt.run_content_hash != ok_run.run_content_hash

    pkg = ROOT / "app" / "services" / "research_data" / "evaluation_platform"
    forbidden = ("trading_db", "submit_order", "production_oms")
    clean = True
    for py in pkg.rglob("*.py"):
        if any(tok in py.read_text(encoding="utf-8") for tok in forbidden):
            clean = False
            break
    checks["no_oms_trading_db"] = clean

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
