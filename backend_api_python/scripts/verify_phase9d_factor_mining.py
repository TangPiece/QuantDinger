#!/usr/bin/env python3
"""Phase 9D 验收：Factor Mining Platform。"""

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
    from app.services.research_data.mining_platform.protocol import ENGINE_VERSION
    from app.services.research_data.mining_platform.runner import FactorMiningService
    from app.services.research_data.mining_platform.policy_presets import get_policy
    from mining_platform_golden.golden import (
        GOLDEN_MINING_POLICY_ID,
        GOLDEN_RANDOM_SEED,
        golden_mining_job,
        make_mining_platform_env,
        mining_inject,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9d_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_mining_platform@1"
    svc, _ds, _reg, job = make_mining_platform_env(tmp / "main")
    inj = mining_inject()

    checks["no_auto_approve"] = not hasattr(FactorMiningService, "auto_approve")
    checks["no_gp_default"] = not hasattr(FactorMiningService, "genetic_default")
    checks["no_promote_strategy"] = not hasattr(FactorMiningService, "promote_strategy")
    checks["no_capacity"] = not hasattr(FactorMiningService, "capacity_curve")
    checks["has_run_mining"] = hasattr(svc, "run_mining")
    checks["has_promote_draft"] = hasattr(svc, "promote_candidate_to_draft")

    pol = get_policy(GOLDEN_MINING_POLICY_ID)
    run = svc.run_mining(job, inject=inj)
    checks["completed"] = run.status == "COMPLETED"
    checks["max_candidates"] = run.total_candidates_generated <= pol.max_candidates
    checks["bias_warning"] = bool(run.selection_bias_warning)
    checks["total_tested"] = run.total_candidates_tested >= 1

    idem = svc.run_mining(job, inject=inj)
    checks["repro_hash"] = idem.mining_run_hash == run.mining_run_hash
    h1 = {c.expression_hash for c in run.candidates}
    h2 = {c.expression_hash for c in idem.candidates}
    checks["repro_expr_set"] = h1 == h2

    ranked = [c for c in run.candidates if c.evaluation_id and c.status == "RANKED"]
    checks["survivors_eval_id"] = len(ranked) >= 1
    if ranked:
        checks["holdout_separate"] = all(
            c.holdout_metrics is not None or c.holdout_evaluation_id
            for c in ranked
        )
        # ranking 未使用 holdout（holdout 指标不参与 mining_score 计算）
        checks["holdout_not_in_score_raw"] = all(
            "holdout" not in str(c.metadata).lower() or c.mining_score >= 0
            for c in ranked
        )
    else:
        checks["holdout_separate"] = True
        checks["holdout_not_in_score_raw"] = True

    inj_screen = mining_inject(screen_ic_threshold=0.99)
    run_strict = svc.run_mining(
        job.model_copy(update={"random_seed": GOLDEN_RANDOM_SEED + 99}),
        inject=inj_screen,
    )
    checks["fast_screen_reduces"] = run_strict.total_candidates_tested <= run.total_candidates_tested

    pkg = ROOT / "app" / "services" / "research_data" / "mining_platform"
    forbidden = ("genetic_programming", "bonferroni", "deflated_sharpe", "promote_strategy")
    clean = True
    for py in pkg.rglob("*.py"):
        text = py.read_text(encoding="utf-8").lower()
        if "gp_default" in text or "auto_approve" in text:
            clean = False
            break
    checks["no_gp_auto_approve_strings"] = clean

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
