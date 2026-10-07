#!/usr/bin/env python3
"""Phase 7B 验收：Live MD + Shadow Trading。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7b_shadow_trading.py
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
    for pkg_name in ("shadow_trading", "live_market_data"):
        pkg = ROOT / "app" / "services" / pkg_name
        for py in pkg.rglob("*.py"):
            if py.name != "transport.py":
                continue
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "request" and node.args:
                        if isinstance(node.args[0], ast.Constant):
                            if str(node.args[0].value).upper() == "POST":
                                return False
    return True


def main() -> int:
    from app.services.live_readonly.modes import EnvironmentTransitionError, assert_transition
    from app.services.oms import cycle as oms_cycle
    from app.services.oms.protocol import Order
    from app.services.research_data.contracts import OrderIntent
    from app.services.shadow_trading.gateway import EnvironmentViolation, OrderExecutionGateway
    from app.services.shadow_trading.oms import ShadowOmsError
    from shadow_trading_golden.golden import ACCOUNT_ID, DATASET_HASH, MODEL_VERSION, STRATEGY_VERSION, make_env

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase7b_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_guard"] = _ast_guard()
    checks["oms_no_live_env"] = "LIVE" not in oms_cycle._ALLOWED_ENV

    class _RealBroker:
        broker_id = "alpaca_live"
        base_url = "https://api.alpaca.markets"

        def submit_order(self, order):
            return order

    gw = OrderExecutionGateway()
    deny = False
    try:
        gw.submit_real(
            "SHADOW",
            Order(order_id="v", client_order_id="v", quantity=1.0),
            _RealBroker(),
            submit_fn=_RealBroker().submit_order,
        )
    except EnvironmentViolation:
        deny = True
    checks["gateway_deny_real_broker"] = deny

    ladder_ok = False
    try:
        assert_transition("PAPER", "LIVE_READONLY", production_ready=True)
    except EnvironmentTransitionError:
        assert_transition("PAPER", "SHADOW", production_ready=True)
        assert_transition("SHADOW", "LIVE_READONLY", production_ready=True)
        ladder_ok = True
    checks["env_ladder"] = ladder_ok

    *_, shadow, _ = make_env(tmp)
    intent = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=5.0,
        execution_algorithm="MARKET",
        trace_id="verify_mkt",
    )
    shadow.submit_intent(intent)
    shadow.simulate_fills_for_symbol("AAPL", bid=99.9, ask=100.1)
    checks["shadow_fill"] = shadow.get_shadow_pnl()["cash"] < 100_000.0

    risk_block = False
    shadow._risk = lambda _i: (False, "NO")
    try:
        shadow.submit_intent(
            OrderIntent(
                instrument_key="USStock:AAPL",
                side="BUY",
                quantity=1.0,
                trace_id="verify_deny",
            )
        )
    except ShadowOmsError:
        risk_block = True
    checks["risk_gate"] = risk_block

    immut = True
    try:
        from app.services.shadow_trading.session import merge_session_update

        merge_session_update(shadow._session, {"dataset_hash": "x"})
        immut = False
    except Exception:
        immut = True
    checks["session_immutable"] = immut

    report = shadow.compare_with_live(ACCOUNT_ID)
    checks["compare_report"] = bool(report.run_id)

    real_get = None
    if os.environ.get("ALPACA_LIVE_API_KEY") and os.environ.get("ALPACA_LIVE_API_SECRET"):
        try:
            from app.services.live_market_data.transport import AlpacaLiveMdTransport

            tr = AlpacaLiveMdTransport()
            real_get = bool(tr.get_latest_quote("AAPL"))
        except Exception:
            real_get = False
    checks["opt_in_real_data_get"] = real_get if real_get is not None else True

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
