#!/usr/bin/env python3
"""Phase 8C 验收：Strategy Validation Gate（Fake inject / LocalJson）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8c_validation_gate.py
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
    from app.services.strategy_validation.protocol import ENGINE_VERSION
    from validation_gate_golden.golden import (
        golden_pass_inject,
        golden_pit_leak_inject,
        make_validation_env,
        validated_candidate,
    )
    from strategy_candidate_golden.golden import REGISTRY_VERSION

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8c_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_strategy_validation@1"

    val_svc, cand_svc, _ = make_validation_env(tmp)
    cand = validated_candidate(cand_svc)
    pin_before = cand.content_hash

    run_pass = val_svc.run(cand.candidate_id, inject=golden_pass_inject(), operator="verify")
    checks["passed_run"] = run_pass.status == "PASSED"
    checks["policy_pinned"] = bool(run_pass.policy_content_hash)

    run_fail = val_svc.run(
        cand.candidate_id,
        inject=golden_pit_leak_inject(),
        policy_id="default_research_v1",
    )
    # 同 policy 幂等：仍应返回首次 PASSED run
    checks["idempotent_same_policy"] = run_fail.validation_id == run_pass.validation_id

    cand_after = cand_svc.get(cand.candidate_id)
    checks["lineage_unchanged"] = cand_after.content_hash == pin_before

    _, prom, ver = cand_svc.promote_to_registry(
        cand.candidate_id,
        target_strategy_version=REGISTRY_VERSION,
    )
    checks["promote_with_passed"] = prom.to_state == "REGISTERED" and bool(ver.version_id)

    ok = all(checks.values())
    print(json.dumps({"phase": "8c", "ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
