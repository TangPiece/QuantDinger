#!/usr/bin/env python3
"""Phase 6G 验收：Safety / Kill Switch。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6g_safety.py
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


def _domain_isolation() -> bool:
    pkg = ROOT / "app" / "services" / "safety_service"
    forbidden = (
        "qlib",
        "strategy_v2",
        "live_trading",
        "pending_order",
        "DataSourceFactory",
    )
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    for frag in forbidden:
                        if frag in name:
                            return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for frag in forbidden:
                    if frag in mod:
                        return False
    return True


def main() -> int:
    from safety_golden.golden import INST_A, make_env, prices, sample_intent
    from app.services.oms import OMSError
    from app.services.safety_service import SafetyService
    from app.services.safety_service.state_machine import SafetyStateError

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6g_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    _, registry, portfolio, oms, safety, recon, *_ = make_env(tmp)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]

    # ALLOW baseline
    r = oms.submit_intents(
        [sample_intent(qty=1, reason="v_allow")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    checks["allow_submit"] = bool(r.orders)

    # UNKNOWN → Fail-Closed
    safety.mark_state_unknown("ACCOUNT", acct.account_id)
    unknown_blocked = False
    try:
        oms.submit_intents(
            [sample_intent(qty=1, reason="v_unknown")],
            account_id=acct.account_id,
            portfolio_id=pid,
            environment="SANDBOX",
            prices=prices(),
        )
    except OMSError:
        unknown_blocked = True
    checks["unknown_fail_closed"] = unknown_blocked

    # 新 env：Global kill + restart persistence
    _, registry2, portfolio2, oms2, safety2, *_ = make_env(tmp / "g2")
    acct2 = portfolio2.open_account(initial_cash=1_000_000)
    pid2 = acct2.metadata["default_portfolio_id"]
    safety2.engage_kill_switch("GLOBAL", "GLOBAL", reason="verify")
    checks["global_kill"] = safety2.is_blocked(acct2.account_id)
    safety3 = SafetyService(None, registry2, portfolio_service=portfolio2, oms_service=oms2)
    checks["restart_halt"] = safety3.is_blocked(acct2.account_id)

    # resume needs ack
    resume_fail = False
    try:
        safety3.resume("GLOBAL", "GLOBAL", operator="op")
    except SafetyStateError:
        resume_fail = True
    checks["resume_needs_ack"] = resume_fail
    safety3.acknowledge("GLOBAL|GLOBAL", operator="op")
    st = safety3.resume("GLOBAL", "GLOBAL", operator="op")
    checks["manual_resume"] = st.state == "NORMAL"

    # Recon CRITICAL → safety block
    _, _, portfolio4, oms4, safety4, recon4, *_ = make_env(tmp / "g3")
    acct4 = portfolio4.open_account(initial_cash=1_000_000)
    pid4 = acct4.metadata["default_portfolio_id"]
    oms4.submit_intents(
        [sample_intent(qty=3, reason="v_recon")],
        account_id=acct4.account_id,
        portfolio_id=pid4,
        environment="SANDBOX",
        prices=prices(),
    )
    oms4.drain_outbox()
    recon4.run(
        acct4.account_id,
        pid4,
        mode="EOD",
        salt="v_crit",
        inject={"force_broker_position": {INST_A: 0.0}},
    )
    checks["recon_critical"] = safety4.is_blocked(acct4.account_id)

    # stale market data
    safety4.set_market_data_age(INST_A, 500.0)
    d = safety4.decide(acct4.account_id, sample_intent(qty=1))
    checks["stale_md"] = d.decision == "BLOCK_NEW_ORDER"

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
