"""Phase 8E：简化 Return Attribution 分解。"""

from __future__ import annotations

from .protocol import MetricDeviation, MetricsSnapshot, ReturnAttribution


def build_return_attribution(
    baseline: MetricsSnapshot,
    actual: MetricsSnapshot,
    deviations: list[MetricDeviation],
) -> ReturnAttribution:
    """用偏差近似分解 bps（观察用，非精确归因引擎）。"""
    ret_delta_bps = (actual.return_total - baseline.return_total) * 10000.0
    cost_bps = (actual.total_cost_bps - baseline.total_cost_bps) * 100.0
    slip_bps = (actual.slippage_bps - baseline.slippage_bps) * 100.0
    timing_bps = (actual.qty_delta - baseline.qty_delta) * 10000.0
    residual = ret_delta_bps - cost_bps - slip_bps - timing_bps
    return ReturnAttribution(
        alpha_bps=ret_delta_bps * 0.4,
        beta_bps=ret_delta_bps * 0.2,
        cost_bps=cost_bps,
        slippage_bps=slip_bps,
        timing_bps=timing_bps,
        residual_bps=residual,
    )


__all__ = ["build_return_attribution"]
