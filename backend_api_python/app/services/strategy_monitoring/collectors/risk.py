"""Phase 8F：Risk 维度 — limit utilization vs RiskPolicy。"""

from __future__ import annotations

from typing import Any, Mapping

from ..identity import build_metric_id
from ..protocol import HealthStatus, MonitoringMetric


def _f(src: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    if key not in src or src[key] is None:
        return default
    try:
        return float(src[key])
    except (TypeError, ValueError):
        return default


def _util_health(util: float) -> HealthStatus:
    if util >= 1.0:
        return "CRITICAL"
    if util >= 0.85:
        return "WARNING"
    return "HEALTHY"


def collect_risk(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
    risk_limits: Mapping[str, float] | None,
) -> list[MonitoringMetric]:
    limits = dict(risk_limits or {})
    max_gross = _f(limits, "max_gross_exposure", 1.0) or 1.0
    max_turn = _f(limits, "max_turnover", 0.30) or 0.30

    gross = _f(section, "gross_exposure", _f(section, "gross_exposure_actual"))
    turnover = _f(section, "turnover", _f(section, "turnover_actual"))
    gross_util = _f(section, "gross_exposure_util", gross / max_gross if max_gross else 0.0)
    turn_util = _f(section, "turnover_util", turnover / max_turn if max_turn else 0.0)

    specs = [
        ("gross_exposure_util", gross_util),
        ("turnover_util", turn_util),
    ]
    out: list[MonitoringMetric] = []
    for name, val in specs:
        out.append(
            MonitoringMetric(
                metric_id=build_metric_id(
                    strategy_code=strategy_code,
                    category="RISK",
                    name=name,
                    collected_at=collected_at,
                ),
                strategy_code=strategy_code,
                category="RISK",
                name=name,
                value=val,
                health=_util_health(val),
                collected_at=collected_at,
                session_id=session_id,
            )
        )
    return out


__all__ = ["collect_risk"]
