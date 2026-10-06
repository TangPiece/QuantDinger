"""基础 Benchmark：单标的日收益累乘（缺失则跳过）。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.backtest.ledger import EquityPoint


def build_benchmark_equity(
    calendar_dates: Sequence[str],
    bars_by_date: Mapping[str, Mapping[str, MarketBar]],
    *,
    benchmark_key: str,
    initial_capital: float,
) -> list[EquityPoint]:
    """用 benchmark 标的 close 相对收益累乘生成基准权益。"""
    if not benchmark_key or initial_capital <= 0:
        return []

    points: list[EquityPoint] = []
    equity = float(initial_capital)
    prev_close: float | None = None
    for day in calendar_dates:
        bars = bars_by_date.get(day) or {}
        bar = bars.get(benchmark_key)
        close = float(bar.close) if bar and bar.close is not None else None
        if close is not None and prev_close is not None and prev_close > 0:
            equity *= close / prev_close
        if close is not None:
            prev_close = close
        points.append(EquityPoint(trading_date=day, equity=equity, drawdown=None))
    return points


def summarize_vs_benchmark(
    strategy: Sequence[EquityPoint],
    benchmark: Sequence[EquityPoint],
) -> dict[str, Any]:
    """计算 excess / 简单 tracking 摘要；不足则空 dict。"""
    if len(strategy) < 2 or len(benchmark) < 2:
        return {}
    s0, s1 = strategy[0].equity, strategy[-1].equity
    b0, b1 = benchmark[0].equity, benchmark[-1].equity
    if s0 <= 0 or b0 <= 0:
        return {}
    strat_ret = s1 / s0 - 1.0
    bench_ret = b1 / b0 - 1.0
    return {
        "benchmark_total_return": bench_ret,
        "strategy_total_return": strat_ret,
        "excess_return": strat_ret - bench_ret,
    }
