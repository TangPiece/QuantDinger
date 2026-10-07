#!/usr/bin/env python3
"""Phase 7D 验收：Controlled Live Production（Fake MD + Fake broker）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7d_controlled_production.py
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
    from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
        FakeControlledLiveAdapter,
    )
    from app.services.controlled_live.gate import ControlledLiveDenied
    from app.services.controlled_live.session import SessionImmutableError, assert_session_immutable
    from app.services.production_runtime.runner import ProductionRuntimeError, ProductionRuntimeService
    from app.services.shadow_trading.gateway import EnvironmentViolation, OrderExecutionGateway
    from controlled_production_golden.golden import (
        STRATEGY_ID,
        FakeReconciliationService,
        make_production_env,
        _limit_intent,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase7d_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    gw = OrderExecutionGateway()
    live_denied = False
    try:
        gw.submit_real("LIVE", None, FakeControlledLiveAdapter(), submit_fn=lambda o: o)
    except EnvironmentViolation:
        live_denied = True
    checks["gateway_live_denied"] = live_denied

    prod_live_denied = False
    try:
        ProductionRuntimeService(None, None).start("b", environment="LIVE")  # type: ignore[arg-type]
    except ProductionRuntimeError:
        prod_live_denied = True
    checks["production_runtime_live_denied"] = prod_live_denied

    _, _, controlled, runtime, broker, md, _, ops = make_production_env(tmp, max_orders=3)

    imm = False
    try:
        assert_session_immutable(controlled._session, {"model_version": "changed"})
    except SessionImmutableError:
        imm = True
    checks["session_immutable"] = imm

    r1 = runtime.tick()
    r2 = runtime.tick()
    checks["multi_tick_submit"] = (
        r1.orders_submitted == 1 and r2.orders_submitted == 1 and broker.submit_count == 2
    )
    checks["filled_session_open"] = controlled._session.status == "OPEN"

    md.set_stale(stale=True)
    stale = runtime.tick()
    checks["md_stale_halt"] = stale.halted and stale.stop_reason == "md_stale"

    _, _, controlled2, runtime2, broker2, _, recon2, _ = make_production_env(
        tmp / "recon", max_orders=3, recon=FakeReconciliationService(critical=True)
    )
    runtime2.tick()
    recon_halt = controlled2._session.stop_reason == "recon_mismatch"
    denied_after = False
    try:
        controlled2.submit_single_intent(_limit_intent(trace="x"), strategy_id=STRATEGY_ID)
    except ControlledLiveDenied:
        denied_after = True
    checks["recon_critical_halt"] = recon_halt and denied_after

    _, _, controlled3, _, broker3, _, _, _ = make_production_env(tmp / "max1", max_orders=1)
    controlled3.submit_single_intent(_limit_intent(trace="only"), strategy_id=STRATEGY_ID)
    second_denied = False
    try:
        controlled3.submit_single_intent(_limit_intent(trace="two", price=99), strategy_id=STRATEGY_ID)
    except ControlledLiveDenied:
        second_denied = True
    checks["max_orders_denied"] = second_denied and broker3.submit_count == 1

    metrics = ops.metrics.snapshot()
    checks["metrics_tick"] = any(k.startswith("controlled_live_tick_total") for k in metrics)

    snap = runtime.status()
    checks["operator_status"] = bool(snap.strategy_lock.get("dataset_hash"))

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
