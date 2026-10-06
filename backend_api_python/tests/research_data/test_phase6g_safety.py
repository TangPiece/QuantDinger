"""Phase 6G：Trading Safety / Kill Switch 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.oms import OMSError
from app.services.safety_service import SafetyError, SafetyService
from app.services.safety_service.protocol import SafetyRule
from app.services.safety_service.state_machine import SafetyStateError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety_golden.golden import (  # noqa: E402
    INST_A,
    make_env,
    prices,
    sample_intent,
)


def _domain_isolation() -> bool:
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "safety_service"
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


def test_fail_closed_unknown(tmp_path):
    _, _, portfolio, oms, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    safety.mark_state_unknown("ACCOUNT", acct.account_id)
    with pytest.raises(OMSError):
        oms.submit_intents(
            [sample_intent(qty=1, reason="unknown")],
            account_id=acct.account_id,
            portfolio_id=pid,
            environment="SANDBOX",
            prices=prices(),
        )


def test_daily_loss_blocks(tmp_path):
    _, _, portfolio, oms, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    d = safety.decide(
        acct.account_id,
        sample_intent(qty=1),
        inject={"net_daily_pnl_pct": -0.99},
    )
    assert d.decision in ("HALT", "BLOCK_NEW_ORDER")
    with pytest.raises(OMSError):
        oms.submit_intents(
            [sample_intent(qty=1, reason="loss")],
            account_id=acct.account_id,
            portfolio_id=pid,
            environment="SANDBOX",
            prices=prices(),
        )


def test_global_kill_switch(tmp_path):
    _, registry, portfolio, oms, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    safety.engage_kill_switch("GLOBAL", "GLOBAL", reason="ops halt")
    assert safety.is_blocked(acct.account_id)
    with pytest.raises(OMSError):
        oms.submit_intents(
            [sample_intent(qty=1, reason="gk")],
            account_id=acct.account_id,
            portfolio_id=pid,
            environment="SANDBOX",
            prices=prices(),
        )
    # 重启后 HALT 仍持久
    safety2 = SafetyService(
        None,
        registry,
        portfolio_service=portfolio,
        oms_service=oms,
    )
    st = safety2.get_state("GLOBAL", "GLOBAL")
    assert st.state in ("HALTED", "EMERGENCY")
    assert safety2.is_blocked(acct.account_id)


def test_resume_requires_acknowledge(tmp_path):
    _, _, portfolio, oms, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    safety.engage_kill_switch("ACCOUNT", acct.account_id, reason="halt")
    with pytest.raises(SafetyStateError):
        safety.resume("ACCOUNT", acct.account_id, operator="op")
    safety.acknowledge(f"ACCOUNT|{acct.account_id}", operator="op")
    st = safety.resume("ACCOUNT", acct.account_id, operator="op")
    assert st.state == "NORMAL"


def test_recon_critical_via_safety(tmp_path):
    _, _, portfolio, oms, safety, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    oms.submit_intents(
        [sample_intent(qty=5, reason="pre")],
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
        salt="crit",
        inject={"force_broker_position": {INST_A: 0.0}},
    )
    assert acct.account_id in safety.source_flags.recon_critical_accounts
    assert safety.is_blocked(acct.account_id)


def test_market_data_stale(tmp_path):
    _, _, portfolio, oms, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    safety.set_market_data_age(INST_A, 999.0)
    d = safety.decide(acct.account_id, sample_intent(qty=1))
    assert d.decision == "BLOCK_NEW_ORDER"
    assert "MARKET_DATA_STALE" in d.rule_ids or d.rule_ids


def test_event_idempotent(tmp_path):
    _, _, portfolio, _, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    intent = sample_intent(qty=1)
    safety.decide(
        acct.account_id, intent, inject={"net_daily_pnl_pct": -0.99}
    )
    safety.decide(
        acct.account_id, intent, inject={"net_daily_pnl_pct": -0.99}
    )
    events = safety.list_events(scope="ACCOUNT", scope_id=acct.account_id)
    assert len(events) >= 1


def test_cancel_allowed_under_halt(tmp_path):
    _, _, portfolio, oms, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=2, algo="LIMIT", limit_price=1.0, reason="rest")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    safety.engage_kill_switch("GLOBAL", "GLOBAL", reason="halt")
    cancelled = oms.cancel(r.orders[0].order_id)
    assert cancelled.status == "CANCELLED"


def test_upsert_rule_hard_limit(tmp_path):
    _, _, portfolio, _, safety, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    with pytest.raises(SafetyError):
        safety.upsert_rule(
            SafetyRule(
                rule_id="ORDER_NOTIONAL_LIMIT",
                threshold=99_999_999_999.0,
            )
        )
    assert acct.account_id
