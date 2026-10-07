#!/usr/bin/env python3
"""Phase 8D 验收：Strategy Promotion Pipeline（Fake inject / LocalJson）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8d_promotion_pipeline.py
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
    from app.services.strategy_promotion.protocol import ENGINE_VERSION
    from app.services.strategy_promotion.runner import PromotionError, StrategyPromotionService
    from promotion_pipeline_golden.golden import (
        golden_promotion_metrics_inject,
        make_promotion_env,
        seed_promoted_registry,
    )
    from strategy_candidate_golden.golden import REGISTRY_VERSION, STRATEGY_CODE

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8d_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_strategy_promotion@1"

    promo, cand_svc, reg_svc, val_svc, gov = make_promotion_env(tmp)
    cand, _, validation_id = seed_promoted_registry(
        cand_svc, reg_svc, val_svc, governance=gov
    )
    pin_before = cand.content_hash

    req = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="SHADOW",
        idempotency_key="verify_shadow_1",
        operator="verify",
    )
    run = promo.execute(req.request_id, inject=golden_promotion_metrics_inject())
    checks["shadow_completed"] = run.status == "COMPLETED" and run.to_environment == "SHADOW"
    checks["policy_pinned"] = bool(run.policy_content_hash)

    run2 = promo.execute(req.request_id, inject=golden_promotion_metrics_inject())
    checks["idempotent_execute"] = run2.pipeline_run_id == run.pipeline_run_id

    cand_after = cand_svc.get(cand.candidate_id)
    checks["lineage_unchanged"] = cand_after.content_hash == pin_before

    skip_ok = False
    try:
        promo.submit_request(
            strategy_code=STRATEGY_CODE,
            candidate_id=cand.candidate_id,
            validation_id=validation_id,
            strategy_version=REGISTRY_VERSION,
            to_environment="LIVE",
            idempotency_key="verify_skip",
            from_environment="SHADOW",
        )
    except PromotionError:
        skip_ok = True
    checks["forbid_shadow_to_live"] = skip_ok

    ok = all(checks.values())
    print(json.dumps({"phase": "8d", "ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
