#!/usr/bin/env python3
"""Phase 8G 验收：Strategy Guardrails（Fake inject / LocalJson）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8g_strategy_guardrails.py
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
    from app.services.strategy_guardrails.decision import new_decision
    from app.services.strategy_guardrails.protocol import ENGINE_VERSION
    from strategy_guardrails_golden.golden import (
        STRATEGY_CODE,
        golden_performance_critical_guardrail_inject,
        golden_recon_emergency_guardrail_inject,
        golden_risk_pause_guardrail_inject,
        golden_slippage_critical_guardrail_inject,
        make_guardrails_env,
        seed_guardrails_baseline,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8g_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_strategy_guardrails@1"

    def _env(name: str):
        return make_guardrails_env(tmp / name)

    gr, mon, fb, promo, cand, reg, val, safety, gov = _env("slip")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="v_slip")
    slip = gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_slippage_critical_guardrail_inject(),
        session_id="verify_slip",
    )
    rt = gr.get_runtime_state(STRATEGY_CODE)
    checks["slippage_throttle"] = "THROTTLE" in slip.actions_applied
    checks["runtime_throttled"] = rt.runtime_status == "THROTTLED"
    checks["lifecycle_live"] = rt.lifecycle_phase == "LIVE"

    gr2, mon2, fb2, promo2, cand2, reg2, val2, safety2, _gov2 = _env("recon")
    seed_guardrails_baseline(mon2, fb2, promo2, cand2, reg2, val2, idempotency_key="v_recon")
    gr2.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_recon_emergency_guardrail_inject(),
        session_id="verify_recon",
    )
    rt2 = gr2.get_runtime_state(STRATEGY_CODE)
    checks["recon_safety_stop"] = rt2.runtime_status == "STOPPED" and bool(safety2.halts)

    gr3, mon3, fb3, promo3, cand3, reg3, val3, _s3, _g3 = _env("perf")
    seed_guardrails_baseline(mon3, fb3, promo3, cand3, reg3, val3, idempotency_key="v_perf")
    perf = gr3.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_performance_critical_guardrail_inject(),
        session_id="verify_perf",
    )
    incs = gr3.list_incidents(STRATEGY_CODE)
    checks["performance_review"] = bool(perf.incidents) and any(
        i.status == "REVIEW_REQUIRED" for i in incs
    )
    checks["no_auto_stop_on_perf"] = "STOP" not in perf.actions_applied

    gr4, mon4, fb4, promo4, cand4, reg4, val4, _s4, _g4 = _env("pause")
    seed_guardrails_baseline(mon4, fb4, promo4, cand4, reg4, val4, idempotency_key="v_pause")
    pause = gr4.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_risk_pause_guardrail_inject(),
        session_id="verify_pause",
    )
    checks["auto_pause_ok"] = "PAUSE" in pause.actions_applied

    stop_dec = new_decision(
        strategy_code=STRATEGY_CODE,
        decision_type="STOP",
        status="PENDING",
    )
    gr4.submit_decision(stop_dec)
    try:
        gr4.execute_approved_decision(stop_dec.decision_id)
        checks["stop_without_approval_rejected"] = False
    except Exception:
        checks["stop_without_approval_rejected"] = True

    gr5, mon5, fb5, promo5, cand5, reg5, val5, _s5, _g5 = _env("rb")
    seed_guardrails_baseline(mon5, fb5, promo5, cand5, reg5, val5, idempotency_key="v_rb")
    rec = gr5.rollback(STRATEGY_CODE, "v_prev", operator="verify", from_version="v_live")
    checks["rollback_lineage"] = rec.from_version == "v_live" and rec.to_version == "v_prev"

    gr6, mon6, fb6, promo6, cand6, reg6, val6, _s6, gov6 = _env("resume")
    seed_guardrails_baseline(mon6, fb6, promo6, cand6, reg6, val6, idempotency_key="v_resume")
    gr6.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_risk_pause_guardrail_inject(),
        session_id="verify_resume_block",
    )
    try:
        gr6.resume(STRATEGY_CODE, operator="verify")
        checks["resume_blocked_until_recovery"] = False
    except Exception:
        checks["resume_blocked_until_recovery"] = True

    checks["capital_no_reallocate"] = bool(gov6._runtime_pause_log)

    ok = all(checks.values())
    print(json.dumps({"phase": "8g", "ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
