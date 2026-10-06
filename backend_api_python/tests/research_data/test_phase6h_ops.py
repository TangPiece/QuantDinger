"""Phase 6H：Monitoring / Audit / Alert 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.ops_service.audit.emit import AppendOnlyConflict
from app.services.ops_service.protocol import AuditActor
from app.services.safety_service import SafetyService

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ops_golden.golden import INST_A, make_env, prices, sample_intent  # noqa: E402


def _domain_isolation() -> bool:
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "ops_service"
    )
    forbidden = (
        "qlib",
        "strategy_v2",
        "live_trading",
        "pending_order",
        "DataSourceFactory",
    )
    for py in root.rglob("*.py"):
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


def test_ast_isolation():
    assert _domain_isolation()


def test_order_fill_trace(tmp_path):
    _, _, portfolio, oms, _, _, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    intent = sample_intent(qty=2, reason="trace")
    tid = intent.trace_id
    r = oms.submit_intents(
        [intent],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="PAPER",
        prices=prices(),
    )
    order = r.orders[0]
    assert order.metadata.get("trace_id") == tid
    chain = ops.get_trace(tid)
    types = {e.event_type for e in chain}
    assert "ORDER_SUBMIT" in types
    assert "EXECUTION_RECEIVED" in types


def test_kill_switch_actor_audit(tmp_path):
    _, _, portfolio, _, safety, _, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    safety.engage_kill_switch(
        "ACCOUNT", acct.account_id, reason="ops test", operator="alice"
    )
    events = ops.list_audit_events(account_id=acct.account_id)
    ks = [e for e in events if e.event_type == "KILL_SWITCH_ON"]
    assert ks and ks[0].actor.actor_id == "alice"


def test_recon_finding_audit_and_safety(tmp_path):
    _, _, portfolio, oms, safety, recon, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    oms.submit_intents(
        [sample_intent(qty=4, reason="recon")],
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
        salt="ops_crit",
        inject={"force_broker_position": {INST_A: 0.0}},
    )
    assert safety.is_blocked(acct.account_id)
    assert any(
        e.event_type == "RECONCILIATION_MISMATCH"
        for e in ops.list_audit_events(account_id=acct.account_id)
    )


def test_config_before_after(tmp_path):
    _, _, portfolio, _, _, _, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    ops.audit_config_change(
        actor=AuditActor(actor_type="OPERATOR", actor_id="bob"),
        entity_type="alert_rule",
        entity_id="BROKER_LATENCY",
        before={"threshold": 500},
        after={"threshold": 800},
        account_id=acct.account_id,
    )
    ev = ops.list_audit_events(event_type="CONFIG_CHANGE")[0]
    assert ev.before.get("threshold") == 500
    assert ev.after.get("threshold") == 800


def test_alert_incident_and_latency_no_halt(tmp_path):
    _, _, portfolio, _, safety, _, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    alerts = ops.evaluate_alerts(
        {"broker_response_latency_ms": 600.0},
        account_id=acct.account_id,
    )
    assert alerts and alerts[0].incident_id
    assert not safety.is_blocked(acct.account_id)


def test_broker_disconnect_health(tmp_path):
    _, _, portfolio, _, _, _, ops, _, broker_conn = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    ops.report_broker_disconnect(account_id=acct.account_id, broker_id="sim")
    snap = ops.collect_health(account_id=acct.account_id)
    assert snap.health.broker.status == "DEGRADED"
    assert any(
        e.event_type == "HEALTH_BROKER_DISCONNECT"
        for e in ops.list_audit_events(account_id=acct.account_id)
    )


def test_broker_recovery(tmp_path):
    _, _, portfolio, _, _, _, ops, _, _ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    ops.report_broker_disconnect(account_id=acct.account_id, broker_id="sim")
    ops.report_broker_recovery(account_id=acct.account_id, broker_id="sim")
    assert any(
        e.event_type == "HEALTH_BROKER_RECOVERY"
        for e in ops.list_audit_events(account_id=acct.account_id)
    )


def test_restart_audit_persists(tmp_path):
    _, registry, portfolio, oms, safety, _, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    safety.engage_kill_switch("GLOBAL", "GLOBAL", operator="persist")
    ops2 = __import__(
        "app.services.ops_service", fromlist=["OpsService"]
    ).OpsService(registry)
    events = ops2.list_audit_events(event_type="KILL_SWITCH_ON")
    assert events


def test_audit_cannot_overwrite(tmp_path):
    _, _, portfolio, _, _, _, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    ops.emit_audit(
        event_type="ORDER_SUBMIT",
        account_id=acct.account_id,
        salt="fixed",
        reason="first",
    )
    with pytest.raises(AppendOnlyConflict):
        ops.emit_audit(
            event_type="ORDER_SUBMIT",
            account_id=acct.account_id,
            salt="fixed",
            reason="second",
        )


def test_critical_unexpected_fill_safety(tmp_path):
    _, _, portfolio, _, safety, _, ops, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    ops.evaluate_alerts(
        {"unexpected_fill": 1.0},
        account_id=acct.account_id,
    )
    assert safety.is_blocked(acct.account_id)
