"""Phase 8F：Portfolio 维度（简化标量）。"""

from __future__ import annotations

from typing import Any, Mapping

from ..identity import build_metric_id
from ..protocol import MonitoringMetric


def _f(src: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    if key not in src or src[key] is None:
        return default
    try:
        return float(src[key])
    except (TypeError, ValueError):
        return default


def collect_portfolio(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
) -> list[MonitoringMetric]:
    exposure = _f(section, "gross_exposure", 0.5)
    return [
        MonitoringMetric(
            metric_id=build_metric_id(
                strategy_code=strategy_code,
                category="PORTFOLIO",
                name="gross_exposure",
                collected_at=collected_at,
            ),
            strategy_code=strategy_code,
            category="PORTFOLIO",
            name="gross_exposure",
            value=exposure,
            health="HEALTHY",
            collected_at=collected_at,
            session_id=session_id,
        )
    ]


__all__ = ["collect_portfolio"]
