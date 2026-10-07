#!/usr/bin/env python3
"""Phase 8H 验收：Production → Research Feedback Loop（Fake inject / LocalJson）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8h_production_research_feedback.py
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
    from app.services.production_research_feedback.protocol import ENGINE_VERSION, ResearchFeedbackQuery
    from app.services.production_research_feedback.runner import ProductionResearchFeedbackError
    from production_research_feedback_golden.golden import (
        STRATEGY_CODE,
        golden_bad_pit_lineage_inject,
        golden_production_feedback_inject,
        make_feedback_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8h_"))
    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_production_research_feedback@1"

    svc, reg, dq = make_feedback_env(tmp / "main")
    inj = golden_production_feedback_inject()
    ds = svc.build_dataset(
        STRATEGY_CODE,
        "PERFORMANCE_FEEDBACK",
        "2025-05-01",
        "2025-06-01",
        inject=inj,
        session_id="verify",
    )
    snap = svc.build_reality_snapshot(
        STRATEGY_CODE, dataset_id=ds.dataset_id, inject=inj, session_id="verify"
    )
    case = svc.record_failure_case(
        STRATEGY_CODE,
        feedback_dataset_id=ds.dataset_id,
        inject=inj,
        summary="verify case",
    )
    checks["dataset_snapshot_case"] = bool(ds.dataset_id and snap.snapshot_id and case.case_id)
    checks["dataset_hash_stable"] = len(ds.dataset_hash) == 64

    try:
        svc.build_reality_snapshot(
            STRATEGY_CODE,
            inject={
                "production_feedback": {
                    **inj["production_feedback"],
                    "metrics": {"return_total": 0.5},
                }
            },
        )
        checks["snapshot_immutable"] = False
    except ProductionResearchFeedbackError:
        checks["snapshot_immutable"] = True

    try:
        svc.build_dataset(
            STRATEGY_CODE,
            "PERFORMANCE_FEEDBACK",
            "2025-05-01",
            "2025-06-01",
            inject=golden_bad_pit_lineage_inject(),
        )
        checks["quality_gate"] = False
    except ProductionResearchFeedbackError:
        checks["quality_gate"] = True

    rows = dq.production_feedback(ResearchFeedbackQuery(strategy_code=STRATEGY_CODE))
    checks["dataquery_read"] = any(r.record_kind == "DATASET" for r in rows)

    hyp = svc.create_hypothesis(
        STRATEGY_CODE,
        "verify hyp",
        failure_case_ids=[case.case_id],
        feedback_dataset_id=ds.dataset_id,
    )
    link = svc.link_experiment(
        "exp_verify_8h",
        strategy_code=STRATEGY_CODE,
        feedback_dataset_id=ds.dataset_id,
        failure_case_ids=[case.case_id],
        incident_ids=[case.incident_id],
        hypothesis_id=hyp.hypothesis_id,
    )
    stored = reg.get_feedback_experiment_link(link.link_id)
    checks["experiment_lineage"] = (
        stored.parent_feedback_dataset_id == ds.dataset_id
        and case.case_id in stored.parent_failure_case_ids_json
    )

    cf = svc.build_counterfactual(snap.snapshot_id, {"name": "shock", "pnl_shock": -50.0})
    actual = svc.get_snapshot(snap.snapshot_id)
    checks["counterfactual_isolated"] = (
        cf.reality_kind == "COUNTERFACTUAL" and actual.pnl_summary.pnl_total == 1000.0
    )

    import ast

    forbidden = ("train_model", "mutate_version", "promote", "submit_order")
    pkg = ROOT / "app" / "services" / "production_research_feedback"
    ok_forbidden = True
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        blob = ast.dump(tree)
        if any(tok in blob for tok in forbidden):
            ok_forbidden = False
            break
    checks["forbidden_api_absent"] = ok_forbidden

    print(json.dumps({"checks": checks, "ok": all(checks.values())}, indent=2, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
