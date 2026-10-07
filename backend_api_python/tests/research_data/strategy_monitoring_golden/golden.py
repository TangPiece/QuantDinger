"""Phase 8F Golden：Fake inject + Strategy Monitoring 脚手架。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.live_performance_feedback.runner import LivePerformanceFeedbackService
from app.services.strategy_monitoring.runner import StrategyMonitoringService
from app.services.strategy_promotion.runner import StrategyPromotionService

from performance_feedback_golden.golden import (
    golden_actual_drift_inject,
    golden_baseline_metrics_inject,
    make_feedback_env,
    seed_completed_promotion,
)
from strategy_candidate_golden.golden import REGISTRY_VERSION, STRATEGY_CODE


def golden_healthy_monitor_inject() -> dict[str, Any]:
    """各维健康 Fake（Health 非 UNKNOWN）。"""
    return {
        "performance": {
            "shadow_drift": 0.02,
            "max_drawdown": 0.04,
        },
        "risk": {
            "gross_exposure_util": 0.40,
            "turnover_util": 0.50,
        },
        "execution": {"reject_rate": 0.02, "slippage_bps": 8.0},
        "signal": {"signal_correlation": 0.98},
        "portfolio": {"gross_exposure": 0.45},
        "market_data": {"staleness_seconds": 30.0},
        "reconciliation": {"critical_finding_count": 0, "severity": "OK"},
        "capacity": {"capacity_util": 0.35},
    }


def golden_risk_recon_critical_inject() -> dict[str, Any]:
    """Risk breach + Recon CRITICAL。"""
    base = golden_healthy_monitor_inject()
    base["risk"] = {"gross_exposure_util": 1.08, "turnover_util": 0.40}
    base["reconciliation"] = {
        "critical_finding_count": 2,
        "severity": "CRITICAL",
    }
    return base


def golden_market_data_critical_inject() -> dict[str, Any]:
    """Performance HEALTHY + MARKET_DATA CRITICAL（验证非加权平均）。"""
    base = golden_healthy_monitor_inject()
    base["market_data"] = {"staleness_seconds": 600.0}
    return base


def make_monitoring_env(
    tmp: Path,
) -> tuple[
    StrategyMonitoringService,
    LivePerformanceFeedbackService,
    StrategyPromotionService,
    Any,
    Any,
    Any,
    Any,
]:
    fb, promo, cand_svc, reg_svc, val_svc, gov = make_feedback_env(tmp)
    mon = StrategyMonitoringService(
        fb._store,
        cand_svc._registry,
        feedback=fb,
    )
    mon._writer._artifacts.root = tmp / "artifacts"
    fb._writer._artifacts.root = tmp / "artifacts"
    return mon, fb, promo, cand_svc, reg_svc, val_svc, gov


def seed_feedback_comparison(
    fb: LivePerformanceFeedbackService,
    promo: StrategyPromotionService,
    cand_svc: Any,
    reg_svc: Any,
    val_svc: Any,
    *,
    idempotency_key: str = "mon_fb_1",
) -> None:
    pid = seed_completed_promotion(
        promo, cand_svc, reg_svc, val_svc, idempotency_key=idempotency_key
    )
    base = fb.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-05-01",
        window_end="2026-05-08",
        idempotency_key="mon_cmp",
        inject=golden_actual_drift_inject(),
    )


__all__ = [
    "REGISTRY_VERSION",
    "STRATEGY_CODE",
    "golden_healthy_monitor_inject",
    "golden_market_data_critical_inject",
    "golden_risk_recon_critical_inject",
    "make_monitoring_env",
    "seed_feedback_comparison",
]
