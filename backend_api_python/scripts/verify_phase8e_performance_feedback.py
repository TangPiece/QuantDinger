#!/usr/bin/env python3
"""Phase 8E 验收：Live Performance Feedback（Fake inject / LocalJson）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8e_performance_feedback.py
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


def main() -> int:
    from app.services.live_performance_feedback.protocol import ENGINE_VERSION
    from app.services.live_performance_feedback.runner import PerformanceFeedbackError
    from performance_feedback_golden.golden import (
        STRATEGY_CODE,
        golden_actual_drift_inject,
        golden_baseline_metrics_inject,
        make_feedback_env,
        seed_completed_promotion,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8e_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_live_performance_feedback@1"

    fb, promo, cand_svc, reg_svc, val_svc, _ = make_feedback_env(tmp)
    pid = seed_completed_promotion(promo, cand_svc, reg_svc, val_svc)
    base = fb.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    checks["freeze_baseline"] = base.immutable and base.pipeline_run_id == pid

    immut_ok = False
    try:
        fb.freeze_baseline_from_promotion(
            pid, metrics_inject={**golden_baseline_metrics_inject(), "sharpe": 0.1}
        )
    except PerformanceFeedbackError:
        immut_ok = True
    checks["baseline_immutable"] = immut_ok

    run = fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-01-01",
        window_end="2026-01-07",
        idempotency_key="verify_win",
        inject=golden_actual_drift_inject(),
    )
    report = fb.get_report(run.run_id)
    checks["comparison_published"] = run.status == "PUBLISHED"
    checks["drift_report"] = bool(report.findings) and report.overall_severity in (
        "WARNING",
        "CRITICAL",
    )
    checks["attribution"] = report.attribution is not None

    run2 = fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-01-01",
        window_end="2026-01-07",
        idempotency_key="verify_win",
        inject=golden_actual_drift_inject(),
    )
    checks["idempotent_run"] = run2.run_id == run.run_id

    scalars = fb.latest_drift_scalars(STRATEGY_CODE)
    checks["latest_scalars"] = scalars.get("shadow_drift", 0) > 0.05

    ok = all(checks.values())
    print(json.dumps({"phase": "8e", "ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
