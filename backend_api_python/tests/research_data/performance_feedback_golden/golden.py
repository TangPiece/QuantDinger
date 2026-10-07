"""Phase 8E Golden：Fake inject + Performance Feedback 脚手架。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.live_performance_feedback.runner import LivePerformanceFeedbackService
from app.services.strategy_promotion.runner import StrategyPromotionService

from promotion_pipeline_golden.golden import (
    golden_promotion_metrics_inject,
    make_promotion_env,
    seed_promoted_registry,
)
from strategy_candidate_golden.golden import REGISTRY_VERSION, STRATEGY_CODE


def golden_baseline_metrics_inject() -> dict[str, Any]:
    """冻结 ExpectedBaseline 用的研究预期快照（Fake）。"""
    return {
        "return_total": 0.10,
        "sharpe": 1.5,
        "max_drawdown": 0.05,
        "turnover": 0.30,
        "slippage_bps": 6.0,
        "total_cost_bps": 10.0,
        "signal_correlation": 0.99,
        "shadow_drift": 0.01,
        "qty_delta": 0.0,
    }


def golden_actual_drift_inject() -> dict[str, Any]:
    """相对 baseline 恶化的实际表现（触发 WARNING/CRITICAL）。"""
    return {
        "return_total": 0.02,
        "sharpe": 0.4,
        "max_drawdown": 0.18,
        "turnover": 0.55,
        "slippage_bps": 40.0,
        "total_cost_bps": 28.0,
        "signal_correlation": 0.72,
        "shadow_drift": 0.20,
        "qty_delta": 0.15,
        "reject_rate": 0.12,
    }


def make_feedback_env(
    tmp: Path,
) -> tuple[
    LivePerformanceFeedbackService,
    StrategyPromotionService,
    Any,
    Any,
    Any,
    Any,
]:
    promo, cand_svc, reg_svc, val_svc, gov = make_promotion_env(tmp)
    fb = LivePerformanceFeedbackService(
        promo._store,
        cand_svc._registry,
        promotion=promo,
    )
    fb._writer._artifacts.root = tmp / "artifacts"
    promo._writer._artifacts.root = tmp / "artifacts"
    # 测试显式 freeze（带 inject）；跳过 8D 自动 freeze 以免钉死默认 metrics
    promo._try_freeze_performance_baseline = lambda _pid: None  # type: ignore[method-assign]
    return fb, promo, cand_svc, reg_svc, val_svc, gov


def seed_completed_promotion(
    promo: StrategyPromotionService,
    cand_svc: Any,
    reg_svc: Any,
    val_svc: Any,
    *,
    idempotency_key: str = "fb_promo_1",
) -> str:
    """返回 pipeline_run_id（COMPLETED）。"""
    cand, _, validation_id = seed_promoted_registry(cand_svc, reg_svc, val_svc)
    req = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="SHADOW",
        idempotency_key=idempotency_key,
    )
    run = promo.execute(req.request_id, inject=golden_promotion_metrics_inject())
    assert run.status == "COMPLETED"
    return run.pipeline_run_id


__all__ = [
    "REGISTRY_VERSION",
    "STRATEGY_CODE",
    "golden_actual_drift_inject",
    "golden_baseline_metrics_inject",
    "make_feedback_env",
    "seed_completed_promotion",
]
