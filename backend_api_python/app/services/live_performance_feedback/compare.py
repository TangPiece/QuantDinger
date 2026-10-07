"""Phase 8E：baseline vs actual 指标偏差计算。"""

from __future__ import annotations

from .protocol import MetricDeviation, MetricsSnapshot


def _rel_delta(baseline: float, actual: float) -> float:
    if baseline == 0:
        return actual
    return (actual - baseline) / abs(baseline)


def compare_metrics(
    baseline: MetricsSnapshot,
    actual: MetricsSnapshot,
) -> list[MetricDeviation]:
    """逐字段对比（六类指标 + shadow_drift）。"""
    fields = (
        "return_total",
        "sharpe",
        "max_drawdown",
        "turnover",
        "gross_exposure",
        "slippage_bps",
        "total_cost_bps",
        "reject_rate",
        "signal_correlation",
        "qty_delta",
        "shadow_drift",
    )
    out: list[MetricDeviation] = []
    for name in fields:
        b = float(getattr(baseline, name))
        a = float(getattr(actual, name))
        delta = a - b
        out.append(
            MetricDeviation(
                metric=name,
                baseline=b,
                actual=a,
                delta=delta,
                rel_delta=_rel_delta(b, a),
            )
        )
    return out


__all__ = ["compare_metrics"]
