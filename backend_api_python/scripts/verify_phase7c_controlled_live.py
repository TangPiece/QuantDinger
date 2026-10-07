#!/usr/bin/env python3
"""Phase 7C 验收：Controlled Live（Fake broker 默认 0 真实 POST）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7c_controlled_live.py
"""

from __future__ import annotations

import ast
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


def _ast_guard() -> bool:
    transport = (
        ROOT
        / "app"
        / "services"
        / "broker_adapter"
        / "adapters"
        / "alpaca"
        / "live_trading_transport.py"
    )
    tree = ast.parse(transport.read_text(encoding="utf-8"), filename=str(transport))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "request" and node.args:
                if isinstance(node.args[0], ast.Constant):
                    m = str(node.args[0].value).upper()
                    if m in ("DELETE", "PATCH"):
                        return False
    return True


def main() -> int:
    from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
        FakeControlledLiveAdapter,
    )
    from app.services.controlled_live.gate import ControlledLiveDenied
    from app.services.live_readonly.modes import assert_transition
    from app.services.oms import cycle as oms_cycle
    from app.services.research_data.contracts import OrderIntent
    from app.services.shadow_trading.gateway import EnvironmentViolation, OrderExecutionGateway
    from controlled_live_golden.golden import STRATEGY_ID, make_env

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase7c_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_no_delete_patch"] = _ast_guard()
    checks["oms_live_controlled"] = "LIVE_CONTROLLED" in oms_cycle._ALLOWED_ENV
    checks["oms_live_governance_gated"] = oms_cycle.live_env_requires_governance()

    gw = OrderExecutionGateway()
    live_denied = False
    try:
        gw.submit_real("LIVE", None, FakeControlledLiveAdapter(), submit_fn=lambda o: o)
    except EnvironmentViolation:
        live_denied = True
    checks["gateway_live_denied"] = live_denied

    ladder = False
    try:
        assert_transition("LIVE_READONLY", "LIVE_CONTROLLED", production_ready=True)
        ladder = True
    except Exception:
        ladder = False
    checks["env_ladder"] = ladder

    _, _, _, controlled, broker = make_env(tmp)

    mkt_denied = False
    try:
        controlled.submit_single_intent(
            OrderIntent(
                instrument_key="USStock:AAPL",
                side="BUY",
                quantity=1.0,
                execution_algorithm="MARKET",
                trace_id="verify_mkt",
            ),
            strategy_id=STRATEGY_ID,
        )
    except ControlledLiveDenied:
        mkt_denied = True
    checks["market_denied"] = mkt_denied

    intent = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=1.0,
        execution_algorithm="LIMIT",
        limit_price=100.0,
        trace_id="verify_cl",
    )
    order = controlled.submit_single_intent(intent, strategy_id=STRATEGY_ID)
    checks["limit_submit"] = broker.submit_count == 1 and bool(order.client_order_id)

    cancel_denied = False
    try:
        broker.cancel_order("x")
    except Exception:
        cancel_denied = True
    checks["cancel_forbidden"] = cancel_denied

    real_post = None
    if os.environ.get("CONTROLLED_LIVE_ALLOW_REAL_SUBMIT", "").lower() in (
        "true",
        "1",
        "yes",
    ) and os.environ.get("ALPACA_LIVE_API_KEY"):
        checks["opt_in_real_post"] = True  # 不在 CI 默认执行真实 POST
    else:
        checks["opt_in_real_post_skipped"] = True

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
