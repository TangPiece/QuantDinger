#!/usr/bin/env python3
"""Phase 8B 验收：Strategy Candidate（Fake research / LocalJson 默认）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8b_strategy_candidate.py
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
    from app.services.strategy_candidate.protocol import ENGINE_VERSION
    from app.services.strategy_candidate.runner import CandidateError
    from strategy_candidate_golden.golden import (
        BACKTEST_HASH,
        CAND_VERSION,
        DATASET_HASH,
        EXPERIMENT_ID,
        REGISTRY_VERSION,
        STRATEGY_CODE,
        STRATEGY_HASH,
        make_candidate_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8b_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_strategy_candidate@1"

    svc, reg_svc, _ = make_candidate_env(tmp)
    cand = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    checks["lineage_fields"] = bool(
        cand.dataset_hash == DATASET_HASH and cand.strategy_hash == STRATEGY_HASH
    )

    cand2 = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    checks["idempotent"] = cand.candidate_id == cand2.candidate_id

    svc.generate(cand.candidate_id)
    svc.start_evaluating(cand.candidate_id)
    svc.mark_ready(cand.candidate_id)
    validated = svc.mark_validated(cand.candidate_id, operator="verify")
    checks["validated_path"] = validated.status == "VALIDATED"

    skip_fail = False
    try:
        svc.mark_validated(
            svc.create_from_research(
                STRATEGY_CODE,
                candidate_version="cv8b_skip",
                experiment_id=EXPERIMENT_ID,
                backtest_hash=BACKTEST_HASH,
                strategy_hash=STRATEGY_HASH,
            ).candidate_id
        )
    except CandidateError:
        skip_fail = True
    checks["no_skip_validated"] = skip_fail

    _, prom, ver = svc.promote_to_registry(
        cand.candidate_id,
        target_strategy_version=REGISTRY_VERSION,
        operator="verify",
        reason="phase8b verify",
        require_gate_passed=False,
    )
    checks["promote_registry"] = prom.to_state == "REGISTERED" and bool(ver.version_id)
    reg_ver = reg_svc.get_version(STRATEGY_CODE, REGISTRY_VERSION)
    checks["registry_pin"] = reg_ver.dataset_hash == DATASET_HASH

    ok = all(checks.values())
    print(json.dumps({"phase": "8b", "ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
