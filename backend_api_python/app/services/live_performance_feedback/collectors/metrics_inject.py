"""Phase 8E：Fake inject 实际指标（CI / verify）。"""

from __future__ import annotations

from typing import Any, Mapping

from ..protocol import MetricsSnapshot


def _f(src: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    if key not in src or src[key] is None:
        return default
    try:
        return float(src[key])
    except (TypeError, ValueError):
        return default


def collect_from_inject(inject: Mapping[str, Any] | None) -> MetricsSnapshot:
    """从 inject dict 构造 Actual MetricsSnapshot。"""
    data = dict(inject or {})
    return MetricsSnapshot(
        return_total=_f(data, "return_total", _f(data, "total_return")),
        sharpe=_f(data, "sharpe"),
        max_drawdown=_f(data, "max_drawdown", _f(data, "live_drawdown", _f(data, "shadow_drawdown"))),
        turnover=_f(data, "turnover"),
        gross_exposure=_f(data, "gross_exposure"),
        slippage_bps=_f(data, "slippage_bps", _f(data, "slippage") * 10000.0 if _f(data, "slippage") < 1 else _f(data, "slippage")),
        total_cost_bps=_f(data, "total_cost_bps"),
        reject_rate=_f(data, "reject_rate"),
        signal_correlation=_f(data, "signal_correlation", 1.0),
        qty_delta=_f(data, "qty_delta"),
        shadow_drift=_f(data, "shadow_drift"),
        extra={k: v for k, v in data.items() if k not in MetricsSnapshot.model_fields},
    )


__all__ = ["collect_from_inject"]
