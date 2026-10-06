"""Phase 5C：Cost & Execution Model 验收（L1/L2/L3）。"""

from __future__ import annotations

import ast
import sys
from datetime import date
from pathlib import Path

import pytest

from app.services.research_data.research_backtest import compute_backtest_hash
from app.services.research_data.research_execution import (
    ResearchExecutionSimulator,
    build_attribution,
    resolve_market_bundle,
)
from app.services.research_data.research_execution.protocol import DailyCostRow

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_execution_golden.golden import (  # noqa: E402
    INST_A,
    NAV0,
    SHASH,
    long_only_targets,
    make_env,
    make_spec,
    price_bars,
    run_bt,
    trading_days,
)


def _final_nav(result) -> float:
    return float(result.frames.nav[-1].nav)


def test_l1_cost_monotone(tmp_path):
    """L1：GROSS ≥ Commission ≥ +Tax ≥ +Slippage。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(4)
    bars = price_bars(days)
    # 买入后清仓，使印花税（卖出）生效
    targets = {
        days[0].isoformat(): [{"instrument_key": INST_A, "target_weight": 1.0}],
        days[2].isoformat(): [],
    }

    r_gross = run_bt(svc, realism="GROSS", days=days, targets=targets, bars=bars)
    r_comm = run_bt(
        svc,
        realism="NET",
        days=days,
        targets=targets,
        bars=bars,
        cost_override={
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.0,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
            "transfer_fee_rate": 0.0,
        },
        rule_override={"lot_size": 1, "t_plus": 0, "limit_up_down": False},
    )
    r_tax = run_bt(
        svc,
        realism="NET",
        days=days,
        targets=targets,
        bars=bars,
        cost_override={
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.001,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
            "transfer_fee_rate": 0.0,
        },
        rule_override={"lot_size": 1, "t_plus": 0, "limit_up_down": False},
    )
    r_slip = run_bt(
        svc,
        realism="NET",
        days=days,
        targets=targets,
        bars=bars,
        cost_override={
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.001,
            "slippage_bps": 10.0,
            "minimum_commission": 0.0,
            "transfer_fee_rate": 0.0,
        },
        rule_override={"lot_size": 1, "t_plus": 0, "limit_up_down": False},
    )
    g, c, t, s = (
        _final_nav(r_gross),
        _final_nav(r_comm),
        _final_nav(r_tax),
        _final_nav(r_slip),
    )
    assert g + 1e-6 >= c >= t - 1e-6
    assert t + 1e-6 >= s


def test_l2_lot_size_floor():
    """L2：非整手向下取整。"""
    days = trading_days(2)
    execution, price_pol, cost, rules = resolve_market_bundle(
        "CN_A",
        research_fill_field="close",
        cost_policy_override={
            "commission_rate": 0.0,
            "stamp_tax_rate": 0.0,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
        },
        trading_rule_override={"lot_size": 100, "t_plus": 0, "limit_up_down": False},
    )
    sim = ResearchExecutionSimulator(execution, rules, cost, price_pol, calendar=days)
    # nav=1550, price=10 → raw qty=155 → floor 100
    price_index = {
        (INST_A, days[0]): {"open": 10.0, "close": 10.0},
        (INST_A, days[1]): {"open": 10.0, "close": 10.0},
    }
    cash, shares, step, _, _ = sim.step_weights(
        trading_date=days[0],
        target_weights={INST_A: 1.0},
        cash=1550.0,
        shares={},
        price_index=price_index,
    )
    assert abs(shares.get(INST_A, 0.0) - 100.0) < 1e-9
    assert any(
        (d.reason or "").startswith("LOT") or d.rejected_quantity > 0
        for d in step.decisions
    ) or shares[INST_A] == 100.0


def test_l2_cash_constraint():
    """L2：现金不足拒买/部分成交。"""
    days = trading_days(2)
    execution, price_pol, cost, rules = resolve_market_bundle(
        "CN_A",
        research_fill_field="close",
        cost_policy_override={
            "commission_rate": 0.0,
            "stamp_tax_rate": 0.0,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
        },
        trading_rule_override={
            "lot_size": 100,
            "t_plus": 0,
            "limit_up_down": False,
            "enforce_cash": True,
        },
    )
    sim = ResearchExecutionSimulator(execution, rules, cost, price_pol, calendar=days)
    price_index = {(INST_A, days[0]): {"open": 10.0, "close": 10.0}}
    # 现金只够买不到 1 手（100*10=1000）
    cash, shares, step, _, fills = sim.step_weights(
        trading_date=days[0],
        target_weights={INST_A: 1.0},
        cash=500.0,
        shares={},
        price_index=price_index,
    )
    assert INST_A not in shares or shares.get(INST_A, 0) == 0
    assert any(f.status == "REJECTED" or f.quantity == 0 for f in fills) or all(
        not d.executable for d in step.decisions
    )


def test_l2_t_plus_blocks_same_day_sell():
    """L2：T+1 当日买入不可卖。"""
    days = trading_days(2)
    execution, price_pol, cost, rules = resolve_market_bundle(
        "CN_A",
        research_fill_field="close",
        cost_policy_override={
            "commission_rate": 0.0,
            "stamp_tax_rate": 0.0,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
        },
        trading_rule_override={
            "lot_size": 1,
            "t_plus": 1,
            "limit_up_down": False,
        },
    )
    sim = ResearchExecutionSimulator(execution, rules, cost, price_pol, calendar=days)
    price_index = {
        (INST_A, days[0]): {"open": 10.0, "close": 10.0},
    }
    cash, shares, _, _, _ = sim.step_weights(
        trading_date=days[0],
        target_weights={INST_A: 1.0},
        cash=10_000.0,
        shares={},
        price_index=price_index,
    )
    assert shares.get(INST_A, 0) > 0
    # 同日清仓 → T+1 拒绝
    cash2, shares2, step2, _, fills2 = sim.step_weights(
        trading_date=days[0],
        target_weights={},
        cash=cash,
        shares=shares,
        price_index=price_index,
    )
    assert shares2.get(INST_A, 0) > 0  # 仍持有
    assert any(
        (f.reject_reason or "") == "T_PLUS" or f.status == "REJECTED" for f in fills2
    ) or any((d.reason or "") == "T_PLUS" for d in step2.decisions)


def test_l2_limit_up_and_suspend(tmp_path):
    """L2：涨停拒买；停牌拒交易。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(3)
    bars = price_bars(days)
    d0 = days[0]
    status = {
        (INST_A, d0): {"is_limit_up": True, "is_suspended": False},
    }
    r = run_bt(
        svc,
        realism="NET",
        days=days,
        targets=long_only_targets(days[:1]),
        bars=bars,
        trading_status=status,
        cost_override={
            "commission_rate": 0.0,
            "stamp_tax_rate": 0.0,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
        },
        rule_override={"lot_size": 1, "t_plus": 0, "limit_up_down": True},
    )
    day0_pos = [p for p in r.frames.positions if p.trading_date == d0]
    assert not day0_pos or all(p.shares == 0 for p in day0_pos)
    assert any(f.get("reject_reason") == "LIMIT_UP" for f in r.frames.fills) or any(
        f.get("status") == "REJECTED" for f in r.frames.fills
    )

    status2 = {(INST_A, d0): {"is_suspended": True}}
    r2 = run_bt(
        svc,
        realism="NET",
        days=days,
        targets=long_only_targets(days[:1]),
        bars=bars,
        trading_status=status2,
        cost_override={
            "commission_rate": 0.0,
            "stamp_tax_rate": 0.0,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
        },
        rule_override={"lot_size": 1, "t_plus": 0, "limit_up_down": False},
    )
    assert any(f.get("reject_reason") == "SUSPENDED" for f in r2.frames.fills)


def test_l3_attribution_and_hash(tmp_path):
    """L3：归因闭合 + hash 随费率变化。"""
    _, registry, svc = make_env(tmp_path)
    days = trading_days(4)
    bars = price_bars(days)
    targets = long_only_targets(days[:2])
    r = run_bt(
        svc,
        realism="NET",
        days=days,
        targets=targets,
        bars=bars,
        cost_override={
            "commission_rate": 0.001,
            "stamp_tax_rate": 0.0,
            "slippage_bps": 0.0,
            "minimum_commission": 0.0,
            "transfer_fee_rate": 0.0,
        },
        rule_override={"lot_size": 1, "t_plus": 0, "limit_up_down": False},
    )
    attr = r.frames.attribution
    assert attr.get("gross_total_return") is not None
    assert attr.get("net_total_return") is not None
    delta = float(attr["delta_return"])
    bd = attr["breakdown"]
    explained = (
        float(bd["commission_drag"])
        + float(bd["stamp_tax_drag"])
        + float(bd["slippage_drag"])
        + float(bd["transfer_fee_drag"])
        + float(bd["unfilled_drag"])
        + float(bd.get("other") or 0)
    )
    assert abs(delta - explained) < 1e-6
    assert registry.get_research_backtest(r.backtest_hash)
    assert r.summary.realism == "NET"
    assert r.summary.attribution_json

    s1 = make_spec(realism="NET", days=days, cost_override={"commission_rate": 0.001})
    s2 = make_spec(realism="NET", days=days, cost_override={"commission_rate": 0.002})
    assert compute_backtest_hash(s1) != compute_backtest_hash(s2)
    s_gross = make_spec(realism="GROSS", days=days)
    assert compute_backtest_hash(s_gross) != compute_backtest_hash(s1)


def test_gross_backward_compatible(tmp_path):
    """默认 GROSS 不破坏 5B 行为。"""
    _, _, svc = make_env(tmp_path)
    r = run_bt(svc, realism="GROSS")
    assert r.frames.metadata.get("realism") == "GROSS"
    assert not r.frames.costs
    assert r.summary.realism == "GROSS"


def test_no_production_engine_import():
    """research_execution / research_backtest 不 import ProductionBacktestEngine。"""
    roots = [
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "research_execution",
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "research_backtest",
    ]
    banned = ("ProductionBacktestEngine", "backtest_production", "pyqlib")
    for root in roots:
        for py in root.glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for b in banned:
                            assert b not in (alias.name or "")
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for b in banned:
                        assert b not in mod
                    for alias in node.names or []:
                        assert alias.name != "ProductionBacktestEngine"


def test_attribution_helper():
    rows = [
        DailyCostRow(
            trading_date=date(2020, 1, 2),
            commission=100.0,
            stamp_tax=50.0,
            slippage=25.0,
            total_cost=175.0,
        )
    ]
    rep = build_attribution(
        initial_nav=10_000.0,
        gross_final_nav=11_000.0,
        net_final_nav=10_800.0,
        cost_rows=rows,
    )
    assert abs(rep.delta_return - 0.02) < 1e-9
    assert abs(rep.breakdown.commission_drag - 0.01) < 1e-9
