#!/usr/bin/env python3
"""Phase 7A 验收：Live Read-only Adapter。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7a_live_readonly.py
"""

from __future__ import annotations

import ast
import inspect
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
    pkg = ROOT / "app" / "services" / "live_readonly"
    for py in pkg.rglob("*.py"):
        if py.name == "transport.py":
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "request" and node.args:
                        if isinstance(node.args[0], ast.Constant):
                            if str(node.args[0].value).upper() == "POST":
                                return False
        text = py.read_text(encoding="utf-8")
        if "from app.services.oms.runner" in text or "OMSService" in text:
            if py.name == "runner.py":
                continue
            if "OMSService" in text and "broker_port" in text:
                return False
    from app.services.live_readonly.adapter import LiveReadonlyAdapter, _forbid_write

    sub = inspect.getsource(LiveReadonlyAdapter.submit_order)
    forbid = inspect.getsource(_forbid_write)
    return "_forbid_write" in sub and "LIVE_READONLY_FORBIDDEN" in forbid


def main() -> int:
    from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError
    from app.services.live_readonly.gate import ProductionReadyError
    from app.services.live_readonly.modes import EnvironmentTransitionError, assert_transition
    from app.services.live_readonly.runner import LiveReadonlyService
    from app.services.oms import cycle as oms_cycle
    from app.services.oms.protocol import Order
    from live_readonly_golden.golden import ACCOUNT_ID, DATASET_HASH, MODEL_VERSION, STRATEGY_VERSION, make_env

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase7a_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_guard"] = _ast_guard()
    checks["oms_no_live_env"] = "LIVE" not in oms_cycle._ALLOWED_ENV

    jump_blocked = False
    try:
        assert_transition("PAPER", "LIVE")
    except EnvironmentTransitionError:
        jump_blocked = True
    checks["paper_to_live_blocked"] = jump_blocked

    paper_lro_block = False
    try:
        assert_transition("PAPER", "LIVE_READONLY", production_ready=True)
    except EnvironmentTransitionError:
        paper_lro_block = True
    checks["paper_to_live_readonly_blocked"] = paper_lro_block

    ladder_ok = False
    try:
        assert_transition("PAPER", "SHADOW", production_ready=True)
        assert_transition("SHADOW", "LIVE_READONLY", production_ready=True)
        ladder_ok = True
    except EnvironmentTransitionError:
        ladder_ok = False
    checks["shadow_ladder_ok"] = ladder_ok

    *_, lro = make_env(tmp)
    ad = lro.adapter
    order = Order(order_id="v", client_order_id="v", quantity=1.0)
    write_blocked = False
    try:
        ad.submit_order(order)
    except BrokerAdapterError as exc:
        write_blocked = exc.code == AdapterErrorCode.LIVE_READONLY_FORBIDDEN
    checks["writes_raise"] = write_blocked

    os.environ.pop("PRODUCTION_READY", None)
    from app.services.research_data.registry import LocalJsonRegistry

    bare = LocalJsonRegistry(root=tmp / "bare_reg")
    bare_ad = __import__(
        "app.services.live_readonly.adapter", fromlist=["fake_adapter"]
    ).fake_adapter()
    bare_svc = LiveReadonlyService(tmp, bare, adapter=bare_ad)
    prod_block = False
    try:
        bare_svc.connect()
    except ProductionReadyError:
        prod_block = True
    checks["no_production_ready_connect_fails"] = prod_block

    os.environ["PRODUCTION_READY"] = "true"
    *_, lro2 = make_env(tmp / "full")
    session = lro2.start_session(
        account_id=ACCOUNT_ID,
        dataset_hash=DATASET_HASH,
        model_version=MODEL_VERSION,
        strategy_version=STRATEGY_VERSION,
    )
    immut = True
    try:
        from app.services.live_readonly.session import merge_session_update

        merge_session_update(session, {"dataset_hash": "x"})
        immut = False
    except Exception:
        immut = True
    checks["session_immutable"] = immut

    snap = lro2.capture_snapshot(account_id=ACCOUNT_ID)
    checks["snapshot_ok"] = bool(snap.snapshot_id)

    real_get = None
    if os.environ.get("ALPACA_LIVE_API_KEY") and os.environ.get("ALPACA_LIVE_API_SECRET"):
        try:
            from app.services.live_readonly.transport import AlpacaLiveReadonlyTransport

            tr = AlpacaLiveReadonlyTransport()
            acct = tr.get_account()
            real_get = bool(acct)
        except Exception:
            real_get = False
    checks["opt_in_real_get"] = real_get if real_get is not None else True

    failed = [k for k, v in checks.items() if not v]
    print(
        json.dumps(
            {"ok": not failed, "checks": checks, "failed": failed},
            indent=2,
        )
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
