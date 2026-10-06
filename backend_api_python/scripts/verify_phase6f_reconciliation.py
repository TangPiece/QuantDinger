#!/usr/bin/env python3
"""Phase 6F 验收：Reconciliation。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6f_reconciliation.py
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
    pkg = ROOT / "app" / "services" / "reconciliation_service"
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
    from reconciliation_golden.golden import (
        INST_A,
        make_env,
        prices,
        sample_intent,
    )
    from app.services.broker_adapter.protocol import BrokerOrderView
    from app.services.oms import OMSError
    from app.services.reconciliation_service import FindingsError

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6f_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    _, _, portfolio, oms, recon, *_ = make_env(tmp)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]

    # MATCH
    r = oms.submit_intents(
        [sample_intent(qty=5, reason="v_match")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    run = recon.run(acct.account_id, pid, mode="EOD", salt="v_match")
    checks["match"] = run.critical_count == 0 and not recon.is_trading_blocked(
        acct.account_id
    )

    # POSITION mismatch → CRITICAL → block
    run2 = recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="v_pos",
        inject={"force_broker_position": {INST_A: 0.0}},
    )
    checks["position_mismatch"] = any(
        f.type == "POSITION_MISMATCH"
        for f in recon.list_findings(run_id=run2.run_id)
    )
    checks["gate_blocked"] = recon.is_trading_blocked(acct.account_id)

    blocked_ok = False
    try:
        oms.submit_intents(
            [sample_intent(qty=1, reason="v_block")],
            account_id=acct.account_id,
            portfolio_id=pid,
            environment="SANDBOX",
            prices=prices(),
        )
    except OMSError:
        blocked_ok = True
    checks["submit_blocked"] = blocked_ok

    # UNEXPECTED + waive forbidden
    _, _, portfolio3, oms3, recon3, *_ = make_env(tmp / "g2")
    acct3 = portfolio3.open_account(initial_cash=1_000_000)
    pid3 = acct3.metadata["default_portfolio_id"]
    run3 = recon3.run(
        acct3.account_id,
        pid3,
        mode="EOD",
        salt="v_unexp",
        inject={
            "inject_open_orders": [
                BrokerOrderView(
                    client_order_id="ghost",
                    quantity=1,
                    status="NEW",
                    instrument_key=INST_A,
                )
            ]
        },
    )
    checks["unexpected_order"] = any(
        f.type == "UNEXPECTED_ORDER"
        for f in recon3.list_findings(run_id=run3.run_id)
    )
    crit = [
        f
        for f in recon3.list_findings(run_id=run3.run_id)
        if f.severity == "CRITICAL"
    ]
    waive_blocked = False
    try:
        recon3.waive(crit[0].finding_id)
    except FindingsError:
        waive_blocked = True
    checks["critical_no_waive"] = waive_blocked

    # resolve clears gate
    for f in crit:
        recon3.acknowledge(f.finding_id)
        recon3.resolve(f.finding_id)
    checks["resolve_clears_gate"] = not recon3.is_trading_blocked(acct3.account_id)

    # cancel still works under gate on first env: clear then re-block with resting
    for f in recon.list_findings(account_id=acct.account_id):
        if f.severity == "CRITICAL" and f.status == "OPEN":
            try:
                recon.acknowledge(f.finding_id)
                recon.resolve(f.finding_id)
            except Exception:
                pass
    # re-open resting + gate
    rr = oms.submit_intents(
        [sample_intent(qty=2, algo="LIMIT", limit_price=1.0, reason="v_cxl")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="v_cxl_gate",
        inject={
            "inject_open_orders": [
                BrokerOrderView(
                    client_order_id="g2",
                    quantity=1,
                    status="NEW",
                    instrument_key=INST_A,
                )
            ]
        },
    )
    cancelled = oms.cancel(rr.orders[0].order_id)
    checks["cancel_under_gate"] = cancelled.status == "CANCELLED"

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
