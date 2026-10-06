"""Phase 5B：Research Backtest Engine 验收。"""

from __future__ import annotations

import ast
import sys
from datetime import date
from pathlib import Path

import pytest

from app.services.research_data.research_backtest import (
    ResearchExecutionPolicy,
    compute_backtest_hash,
)
from app.services.research_data.research_backtest.execution import (
    map_targets_to_execution,
)
from app.services.research_data.research_backtest.calendar import (
    next_trading_day,
    trading_calendar_from_bars,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_backtest_golden.golden import (  # noqa: E402
    INST_A,
    INST_B,
    INST_BENCH,
    SHASH,
    default_spec,
    long_only_targets,
    long_short_targets,
    make_env,
    price_bars,
    run_backtest,
    trading_days,
)


def test_next_open_execution_timing(tmp_path):
    """NEXT_OPEN：执行日 = 信号日下一交易日；fill 用 open。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(4)
    # 仅 D0 信号 → 应在 D1 开盘执行
    targets = {days[0].isoformat(): [{"instrument_key": INST_A, "target_weight": 1.0}]}
    bars = price_bars(
        days,
        a_open=[10.0, 11.0, 12.0, 13.0],
        a_close=[10.5, 11.5, 12.5, 13.5],
    )
    r = run_backtest(
        svc,
        spec=default_spec(mode="NEXT_OPEN", days=days),
        targets=targets,
        bars=bars,
    )
    assert r.frames.metadata["fill_field"] == "open"
    # D0 无仓；D1 起持有 A
    by_date = {}
    for p in r.frames.positions:
        by_date.setdefault(p.trading_date, {})[p.instrument_key] = p.shares
    assert INST_A not in by_date.get(days[0], {})
    assert INST_A in by_date.get(days[1], {})
    # shares = nav(=1) * 1 / open_D1
    assert abs(by_date[days[1]][INST_A] - 1.0 / 11.0) < 1e-9


def test_same_close_allows_same_day(tmp_path):
    """SAME_CLOSE：当日收盘成交，manifest 标记 allows_same_close。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(3)
    targets = {days[0].isoformat(): [{"instrument_key": INST_A, "target_weight": 1.0}]}
    r = run_backtest(
        svc,
        spec=default_spec(mode="SAME_CLOSE", days=days),
        targets=targets,
        bars=price_bars(days),
    )
    assert r.summary.metadata.get("allows_same_close") is True
    by_date = {p.trading_date for p in r.frames.positions}
    assert days[0] in by_date


def test_long_only_nav_hand_calc(tmp_path):
    """Long-only：NEXT_OPEN 后收盘盯市可手算。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(3)
    # D0 signal → D1 open fill @11, close@12 → return D1→D2
    bars = price_bars(
        days,
        a_open=[10.0, 11.0, 12.0],
        a_close=[10.0, 12.0, 14.0],
    )
    targets = {days[0].isoformat(): [{"instrument_key": INST_A, "target_weight": 1.0}]}
    r = run_backtest(
        svc,
        spec=default_spec(mode="NEXT_OPEN", days=days),
        targets=targets,
        bars=bars,
    )
    nav_by = {n.trading_date: n.nav for n in r.frames.nav}
    # D0: 空仓 cash=1
    assert abs(nav_by[days[0]] - 1.0) < 1e-9
    # D1: shares=1/11, close=12 → nav=12/11
    assert abs(nav_by[days[1]] - 12.0 / 11.0) < 1e-9
    # D2: same shares, close=14 → nav=14/11
    assert abs(nav_by[days[2]] - 14.0 / 11.0) < 1e-9


def test_long_short_negative_shares(tmp_path):
    """Long-short：正负 shares 共存。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(3)
    r = run_backtest(
        svc,
        spec=default_spec(mode="SAME_CLOSE", days=days),
        targets=long_short_targets(days[:1]),
        bars=price_bars(days),
    )
    day0 = [p for p in r.frames.positions if p.trading_date == days[0]]
    signs = {p.instrument_key: p.shares for p in day0}
    assert signs[INST_A] > 0
    assert signs[INST_B] < 0


def test_missing_price_skip_to_cash(tmp_path):
    """缺 fill 价：该票 SKIP_TO_CASH。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(3)
    bars = price_bars(days)
    # 去掉 B 在执行日的 open/close → B 无法建仓
    bars = [
        b
        for b in bars
        if not (b["instrument_key"] == INST_B and b["trading_date"] == days[0].isoformat())
    ]
    targets = {
        days[0].isoformat(): [
            {"instrument_key": INST_A, "target_weight": 0.5},
            {"instrument_key": INST_B, "target_weight": 0.5},
        ]
    }
    r = run_backtest(
        svc,
        spec=default_spec(mode="SAME_CLOSE", days=days),
        targets=targets,
        bars=bars,
    )
    day0 = {p.instrument_key: p for p in r.frames.positions if p.trading_date == days[0]}
    assert INST_A in day0
    assert INST_B not in day0
    # 一半权重进现金
    nav0 = next(n for n in r.frames.nav if n.trading_date == days[0])
    assert nav0.cash > 0.4


def test_benchmark_index_excess(tmp_path):
    """INDEX 基准：excess_return 有值。"""
    _, _, svc = make_env(tmp_path)
    days = trading_days(4)
    r = run_backtest(
        svc,
        spec=default_spec(mode="SAME_CLOSE", days=days, benchmark_mode="INDEX"),
        targets=long_only_targets(days[:2]),
        bars=price_bars(days, include_bench=True),
    )
    excess = [
        x.excess_return
        for x in r.frames.returns
        if x.excess_return is not None and x.excess_return == x.excess_return
    ]
    assert excess
    assert r.frames.benchmark_metrics.get("excess")


def test_hash_repro_and_manifest(tmp_path):
    """backtest_hash 可复现；manifest 落盘；不改 5A strategy 源。"""
    _, registry, svc = make_env(tmp_path)
    days = trading_days(3)
    spec = default_spec(days=days)
    h1 = compute_backtest_hash(spec)
    h2 = compute_backtest_hash(spec)
    assert h1 == h2
    r = run_backtest(svc, spec=spec, targets=long_only_targets(days[:1]))
    assert r.backtest_hash == h1
    art = Path(r.summary.storage_uri)
    assert (art / "manifest.json").is_file()
    assert (art / "metrics" / "summary.json").is_file()
    assert registry.get_research_backtest(h1)
    # 5A 未写入
    with pytest.raises(KeyError):
        registry.get_strategy_research(SHASH)


def test_map_execution_next_gt_signal():
    """单元：NEXT_* 下 execution_date > signal_date。"""
    days = trading_days(5)
    cal = days
    targets = {
        days[0]: [{"instrument_key": INST_A, "target_weight": 1.0}],
        days[1]: [{"instrument_key": INST_A, "target_weight": 0.5}],
    }
    mapped = map_targets_to_execution(
        targets, cal, ResearchExecutionPolicy(mode="NEXT_OPEN")
    )
    for sig in targets:
        exec_d = next_trading_day(cal, sig)
        assert exec_d is not None and exec_d > sig
        assert exec_d in mapped


def test_no_production_engine_import():
    """静态约定：research_backtest 包不 import production / simulator / qlib。"""
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "research_backtest"
    )
    banned_mods = ("backtest_production", "backtest.execution", "pyqlib", "qlib")
    banned_names = ("ExecutionSimulator", "ProductionBacktestEngine")
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for b in banned_mods:
                        assert b not in (alias.name or ""), f"{py.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for b in banned_mods:
                    assert b not in mod, f"{py.name} imports from {mod}"
                for alias in node.names or []:
                    for b in banned_names:
                        assert alias.name != b, f"{py.name} imports {b}"


def test_calendar_from_bars():
    days = trading_days(3)
    bars = price_bars(days)
    cal = trading_calendar_from_bars(bars, start=days[0], end=days[-1])
    assert cal == days
