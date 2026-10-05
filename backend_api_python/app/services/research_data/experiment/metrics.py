"""Experiment 基础指标聚合（禁止回测收益类指标）。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import Signal

# Phase 2F 禁止写入的回测收益指标名
_FORBIDDEN_METRIC_KEYS = frozenset(
    {
        "cagr",
        "sharpe",
        "max_drawdown",
        "maxdrawdown",
        "commission",
        "slippage",
        "annual_return",
        "total_return",
    }
)


def assert_no_backtest_metrics(metrics: dict[str, Any]) -> None:
    """拒绝回测收益类指标混入 Experiment metrics。"""
    for key in metrics:
        if str(key).lower().replace("-", "_") in _FORBIDDEN_METRIC_KEYS:
            raise ValueError(f"backtest metric not allowed in Phase 2F: {key!r}")


def signal_counts(signals: list[Signal]) -> dict[str, float]:
    """Signal 方向计数。"""
    long_c = short_c = flat_c = 0
    for s in signals:
        if s.direction == "LONG":
            long_c += 1
        elif s.direction == "SHORT":
            short_c += 1
        else:
            flat_c += 1
    return {
        "long_count": float(long_c),
        "short_count": float(short_c),
        "flat_count": float(flat_c),
        "signal_rows": float(len(signals)),
    }


def merge_experiment_metrics(
    *,
    train_metrics: dict[str, Any],
    signals: list[Signal],
    cash_weight: float,
    n_positions: int,
) -> dict[str, float]:
    """合并 valid 训练指标与 signal 侧基础计数。"""
    out: dict[str, float] = {}
    for k, v in (train_metrics or {}).items():
        if isinstance(v, (int, float)):
            out[str(k)] = float(v)
    out.update(signal_counts(signals))
    out["cash_weight"] = float(cash_weight)
    out["n_positions"] = float(n_positions)
    assert_no_backtest_metrics(out)
    return out
