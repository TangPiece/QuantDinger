"""Phase 6B：Portfolio & Position Service 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.portfolio_service import (
    PortfolioServiceError,
)
from app.services.portfolio_service.corporate_action import CorporateAction
from app.services.portfolio_service.delta import compute_position_deltas
from app.services.portfolio_service.protocol import Position
from app.services.portfolio_service.reconciliation import compare
from app.services.portfolio_service.reducer import apply_event, assert_invariants
from app.services.portfolio_service.events import make_event
from app.services.portfolio_service.protocol import Account, CashBalance, Portfolio, PortfolioState
from app.services.portfolio_service.state_machine import assert_transition, can_transition
from app.services.portfolio_service.state_machine import PortfolioStateError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portfolio_service_golden.golden import (  # noqa: E402
    DAY,
    INST_A,
    INST_B,
    make_env,
    price_bars,
    prices,
    targets,
)


def test_state_machine():
    assert can_transition("ACTIVE", "PAUSED")
    assert_transition("ACTIVE", "RECONCILIATION_REQUIRED")
    with pytest.raises(PortfolioStateError):
        assert_transition("CLOSED", "ACTIVE")


def test_qty_invariant_freeze():
    acct = Account(
        account_id="a1",
        cash=CashBalance(available_cash=100_000),
        equity=100_000,
    )
    pf = Portfolio(portfolio_id="p1", account_id="a1")
    state = PortfolioState(
        account=acct,
        portfolio=pf,
        positions={
            INST_A: Position(
                instrument_key=INST_A,
                quantity=1000,
                available_quantity=1000,
                frozen_quantity=0,
                avg_cost=10.0,
            )
        },
    )
    ev = make_event(
        portfolio_id="p1",
        account_id="a1",
        event_type="FREEZE",
        instrument_key=INST_A,
        quantity=300,
        salt="fz1",
    )
    apply_event(state, ev)
    pos = state.positions[INST_A]
    assert pos.quantity == 1000
    assert pos.frozen_quantity == 300
    assert pos.available_quantity == 700
    assert_invariants(state)


def test_open_account_and_apply_paper(tmp_path):
    _, registry, svc = make_env(tmp_path)
    acct = svc.open_account(environment="PAPER", initial_cash=1_000_000)
    assert acct.status == "ACTIVE"
    assert acct.cash.available_cash == 1_000_000
    pid = acct.metadata["default_portfolio_id"]
    svc.bind_runtime(acct.account_id, "rt_test", bundle_hash="bh1")

    result = svc.apply_targets(
        acct.account_id,
        targets(),
        runtime_id="rt_test",
        run_id="run1",
        trading_date=DAY.isoformat(),
        prices=prices(),
        metadata={"price_bars": price_bars()},
    )
    assert result.status == "OK"
    assert len(result.deltas) >= 1
    assert any(e.event_type == "BUY_FILLED" for e in result.events)
    assert result.snapshot is not None
    assert result.snapshot.equity > 0
    assert result.exposure.gross_exposure > 0
    positions = svc.get_positions(pid)
    assert any(p.instrument_key == INST_A and p.quantity > 0 for p in positions)
    # available + frozen == quantity
    for p in positions:
        assert abs(p.quantity - (p.available_quantity + p.frozen_quantity)) < 1e-6


def test_idempotent_apply(tmp_path):
    _, _, svc = make_env(tmp_path)
    acct = svc.open_account(initial_cash=1_000_000)
    t = targets()
    r1 = svc.apply_targets(
        acct.account_id,
        t,
        runtime_id="rt",
        run_id="run1",
        trading_date=DAY.isoformat(),
        prices=prices(),
    )
    r2 = svc.apply_targets(
        acct.account_id,
        t,
        runtime_id="rt",
        run_id="run1",
        trading_date=DAY.isoformat(),
        prices=prices(),
    )
    assert r1.status == "OK"
    assert r2.status == "SKIPPED_IDEMPOTENT"
    assert r2.reused
    assert r2.apply_id == r1.apply_id


def test_shadow_dry_no_fills(tmp_path):
    _, _, svc = make_env(tmp_path)
    acct = svc.open_account(environment="SHADOW", initial_cash=1_000_000)
    r = svc.apply_targets(
        acct.account_id,
        targets(),
        trading_date=DAY.isoformat(),
        prices=prices(),
        apply_mode="SHADOW_DRY",
    )
    assert r.status == "OK"
    assert r.apply_mode == "SHADOW_DRY"
    assert all(e.event_type != "BUY_FILLED" for e in r.events)
    assert len(r.deltas) >= 1


def test_target_delta_math():
    pos = {
        INST_A: Position(
            instrument_key=INST_A,
            quantity=500,
            available_quantity=500,
            market_value=5000,
            avg_cost=10,
        )
    }
    deltas = compute_position_deltas(
        targets(w_a=0.4, w_b=0.0),
        pos,
        equity=100_000,
        prices=prices(),
    )
    by = {d.instrument_key: d for d in deltas}
    assert INST_A in by
    assert by[INST_A].side == "BUY"
    assert by[INST_A].target_quantity == pytest.approx(4000.0)  # 0.4*100000/10


def test_corporate_action_split(tmp_path):
    _, _, svc = make_env(tmp_path)
    acct = svc.open_account(initial_cash=1_000_000)
    svc.apply_targets(
        acct.account_id,
        targets(w_a=0.2, w_b=0.0),
        trading_date=DAY.isoformat(),
        prices=prices(),
        runtime_id="rt",
        run_id="pre_ca",
    )
    # 再 apply 带 CA
    r = svc.apply_targets(
        acct.account_id,
        targets(w_a=0.2, w_b=0.0),
        trading_date=DAY.isoformat(),
        prices=prices(),
        runtime_id="rt",
        run_id="with_ca",
        corporate_actions=[
            CorporateAction(
                instrument_key=INST_A,
                effective_date=DAY.isoformat(),
                action_type="split",
                split_ratio=2.0,
            )
        ],
        metadata={"force_new_apply": True},
    )
    assert any(e.event_type == "CORPORATE_ACTION" for e in r.events)


def test_reconciliation_mismatch(tmp_path):
    _, _, svc = make_env(tmp_path)
    acct = svc.open_account(initial_cash=100_000)
    report = svc.reconcile(
        acct.account_id,
        external_cash={"available_cash": 99_000, "frozen_cash": 0},
        mark_status=True,
    )
    assert report.status == "RECONCILIATION_REQUIRED"
    updated = svc.get_account(acct.account_id)
    assert updated.status == "RECONCILIATION_REQUIRED"


def test_live_env_rejected(tmp_path):
    _, _, svc = make_env(tmp_path)
    with pytest.raises(PortfolioServiceError):
        svc.open_account(environment="LIVE")  # type: ignore[arg-type]


def test_domain_ast_isolation():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "portfolio_service"
    )
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    assert name != "qlib" and not name.startswith("qlib.")
                    assert "broker" not in name.lower()
                    assert "PendingOrder" not in name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("qlib")
                assert "pending_order" not in mod.lower()
                assert "broker" not in mod.lower()
                assert "strategy_v2" not in mod
                for alias in node.names or []:
                    assert alias.name not in (
                        "PendingOrderWorker",
                        "DataSourceFactory",
                    )
