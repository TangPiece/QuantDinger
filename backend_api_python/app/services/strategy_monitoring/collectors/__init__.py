"""Phase 8F：Monitoring collectors。"""

from __future__ import annotations

from typing import Any, Mapping

from ..protocol import MonitoringMetric, MonitorPolicyRecord
from .capacity import collect_capacity
from .execution import collect_execution
from .market_data import collect_market_data
from .metrics_inject import merge_inject_sections
from .performance import collect_performance
from .portfolio import collect_portfolio
from .reconciliation import collect_reconciliation
from .risk import collect_risk
from .signal import collect_signal


def collect_all_metrics(
    *,
    strategy_code: str,
    collected_at: str,
    session_id: str,
    policy: MonitorPolicyRecord,
    inject: Mapping[str, Any] | None,
    feedback_scalars: Mapping[str, float] | None,
    risk_limits: Mapping[str, float] | None,
    recon_inject: Mapping[str, Any] | None,
) -> list[MonitoringMetric]:
    """汇总各 collector（Fake inject 优先）。"""
    sections = merge_inject_sections(inject)
    out: list[MonitoringMetric] = []
    out.extend(
        collect_performance(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("performance") or {},
            feedback_scalars=feedback_scalars,
        )
    )
    out.extend(
        collect_risk(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("risk") or {},
            risk_limits=risk_limits,
        )
    )
    out.extend(
        collect_execution(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("execution") or {},
        )
    )
    out.extend(
        collect_signal(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("signal") or {},
            feedback_scalars=feedback_scalars,
        )
    )
    out.extend(
        collect_portfolio(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("portfolio") or {},
        )
    )
    out.extend(
        collect_market_data(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("market_data") or {},
            policy=policy,
        )
    )
    out.extend(
        collect_reconciliation(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("reconciliation") or {},
            recon_inject=recon_inject,
        )
    )
    out.extend(
        collect_capacity(
            strategy_code,
            collected_at=collected_at,
            session_id=session_id,
            section=sections.get("capacity") or {},
        )
    )
    return out


__all__ = ["collect_all_metrics"]
