"""组装 Qlib backtest 配置：起止日、benchmark、日频 SimulatorExecutor。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.research_data.backtest.request import BacktestRequest


def _zero_benchmark_series(start: str, end: str) -> pd.Series:
    """golden 无指数时用零收益 Series 充当 benchmark，避免 Qlib 默认 SH000300。

    Qlib ``PortfolioMetrics._cal_benchmark`` 在 ``benchmark_config={}`` 时仍回退 CSI300；
    传入显式 Series 可跳过指数读盘。
    """
    try:
        from qlib.data import D

        cal = D.calendar(start_time=start, end_time=end, freq="day")
        idx = pd.DatetimeIndex(cal)
    except Exception:
        idx = pd.date_range(start=start, end=end, freq="B")
    return pd.Series(0.0, index=idx, name="bench")


def resolve_benchmark(request: BacktestRequest) -> Any:
    """Request.benchmark 为空 → 零收益 Series；否则原样（字符串指数代码）。"""
    if request.benchmark:
        return request.benchmark
    return _zero_benchmark_series(request.start_date, request.end_date)


def build_backtest_config(
    request: BacktestRequest,
    *,
    strategy: Any,
    exchange_kwargs: dict[str, Any],
) -> dict[str, Any]:
    """组装传给 ``qlib.backtest.backtest`` 的参数字典。

    golden 无基准指数时用零收益 Series，跳过真实基准指标。
    """
    from qlib.backtest.executor import SimulatorExecutor

    executor = SimulatorExecutor(
        time_per_step="day",
        generate_portfolio_metrics=True,
        verbose=False,
    )
    return {
        "start_time": request.start_date,
        "end_time": request.end_date,
        "strategy": strategy,
        "executor": executor,
        "benchmark": resolve_benchmark(request),
        "account": float(request.initial_capital),
        "exchange_kwargs": exchange_kwargs,
    }
