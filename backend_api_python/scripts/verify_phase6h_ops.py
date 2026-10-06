#!/usr/bin/env python3
"""Phase 6H 验收：Monitoring / Audit / Alert。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase6h_ops.py
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
    pkg = ROOT / "app" / "services" / "ops_service"
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
    from ops_golden.golden import INST_A, make_env, prices, sample_intent
    from app.services.ops_service import OpsService
    from app.services.ops_service.audit.emit import AppendOnlyConflict
    from app.services.ops_service.protocol import AuditActor

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6h_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    _, registry, portfolio, oms, safety, recon, ops, _, broker_conn = make_env(tmp)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]

    intent = sample_intent(qty=1, reason="v_trace")
    tid = intent.trace_id
    r = oms.submit_intents(
        [intent],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="PAPER",
        prices=prices(),
    )
    chain = ops.get_trace(tid)
    checks["order_trace"] = bool(chain) and r.orders[0].metadata.get("trace_id") == tid

    safety.engage_kill_switch("ACCOUNT", acct.account_id, operator="verify_op")
    checks["kill_actor"] = any(
        e.event_type == "KILL_SWITCH_ON" and e.actor.actor_id == "verify_op"
        for e in ops.list_audit_events(account_id=acct.account_id)
    )

    _, _, portfolio2, oms2, safety2, recon2, ops2, *_ = make_env(tmp / "recon")
    acct2 = portfolio2.open_account(initial_cash=1_000_000)
    pid2 = acct2.metadata["default_portfolio_id"]
    oms2.submit_intents(
        [sample_intent(qty=2, reason="v_recon")],
        account_id=acct2.account_id,
        portfolio_id=pid2,
        environment="SANDBOX",
        prices=prices(),
    )
    oms2.drain_outbox()
    recon2.run(
        acct2.account_id,
        pid2,
        mode="EOD",
        salt="v_crit",
        inject={"force_broker_position": {INST_A: 0.0}},
    )
    checks["recon_audit"] = any(
        e.event_type == "RECONCILIATION_MISMATCH"
        for e in ops2.list_audit_events(account_id=acct2.account_id)
    )
    checks["recon_safety"] = safety2.is_blocked(acct2.account_id)

    ops.audit_config_change(
        actor=AuditActor(actor_type="OPERATOR", actor_id="cfg"),
        entity_type="rule",
        entity_id="X",
        before={"a": 1},
        after={"a": 2},
    )
    checks["config_audit"] = bool(ops.list_audit_events(event_type="CONFIG_CHANGE"))

    _, _, portfolio_lat, _, safety_lat, _, ops_lat, *_ = make_env(tmp / "lat")
    acct_lat = portfolio_lat.open_account(initial_cash=1_000_000)
    alerts = ops_lat.evaluate_alerts(
        {"broker_response_latency_ms": 999.0}, account_id=acct_lat.account_id
    )
    checks["alert_incident"] = bool(alerts and alerts[0].incident_id)
    checks["latency_no_halt"] = not safety_lat.is_blocked(acct_lat.account_id)

    ops.report_broker_disconnect(account_id=acct.account_id, broker_id="sim")
    snap = ops.collect_health(account_id=acct.account_id)
    checks["broker_health"] = snap.health.broker.status == "DEGRADED"
    ops.report_broker_recovery(account_id=acct.account_id, broker_id="sim")
    checks["broker_recovery"] = any(
        e.event_type == "HEALTH_BROKER_RECOVERY"
        for e in ops.list_audit_events(account_id=acct.account_id)
    )

    ops3 = OpsService(registry)
    checks["restart_persist"] = bool(ops3.list_audit_events(event_type="KILL_SWITCH_ON"))

    overwrite_blocked = False
    try:
        ops.emit_audit(event_type="T", salt="dup", reason="a")
        ops.emit_audit(event_type="T", salt="dup", reason="b")
    except AppendOnlyConflict:
        overwrite_blocked = True
    checks["audit_append_only"] = overwrite_blocked

    _, _, portfolio4, _, safety4, _, ops4, *_ = make_env(tmp / "uf")
    acct4 = portfolio4.open_account(initial_cash=1_000_000)
    ops4.evaluate_alerts({"unexpected_fill": 1.0}, account_id=acct4.account_id)
    checks["critical_safety_policy"] = safety4.is_blocked(acct4.account_id)

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
