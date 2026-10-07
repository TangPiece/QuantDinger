#!/usr/bin/env python3
"""Phase 7E 验收：Trading Governance / Gradual Scale（Fake 默认）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7e_gradual_scale.py
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
    from app.services.live_readonly.modes import assert_transition
    from app.services.oms import cycle as oms_cycle
    from app.services.shadow_trading.gateway import EnvironmentViolation, OrderExecutionGateway
    from app.services.trading_governance.protocol import ENGINE_VERSION
    from gradual_scale_golden.golden import ACCOUNT_A, STRATEGY_A, make_governance_env, seed_l1_controlled

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase7e_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_governance@1"
    checks["oms_live_in_allowed_env"] = "LIVE" in oms_cycle._ALLOWED_ENV

    gw = OrderExecutionGateway()
    live_denied = False
    try:
        from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
            FakeControlledLiveAdapter,
        )

        gw.submit_real("LIVE", None, FakeControlledLiveAdapter(), submit_fn=lambda o: o)
    except EnvironmentViolation:
        live_denied = True
    checks["gateway_live_requires_governance"] = live_denied

    ladder_blocked = False
    try:
        assert_transition("LIVE_CONTROLLED", "LIVE", production_ready=True)
    except Exception:
        ladder_blocked = True
    checks["modes_live_controlled_to_live_blocked_default"] = ladder_blocked

    gov, _ = make_governance_env(tmp)
    seed_l1_controlled(gov)
    appr = gov.request_scale_up(STRATEGY_A, account_id=ACCOUNT_A)
    auto_applied = False
    try:
        gov.apply_scale(STRATEGY_A, approval_id=appr.approval_id)
        auto_applied = True
    except Exception:
        auto_applied = False
    checks["scale_no_auto_apply_without_approve"] = not auto_applied

    t1, t2 = __import__(
        "gradual_scale_golden.golden", fromlist=["two_strategy_targets"]
    ).two_strategy_targets()
    agg = gov.aggregate_targets([t1, t2], account_id=ACCOUNT_A)
    checks["aggregation_net_300"] = (
        len(agg) == 1 and abs(agg[0].net_quantity - 300.0) < 1e-6
    )

    ok = all(checks.values())
    print(json.dumps({"phase": "7e", "ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
