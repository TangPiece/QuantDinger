"""Phase 8C Golden：Fake inject + Candidate/Validation 脚手架。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.contracts import CrossValidationSummary
from app.services.research_data.registry import LocalJsonRegistry
from app.services.strategy_candidate.runner import StrategyCandidateService
from app.services.strategy_registry.runner import StrategyRegistryService
from app.services.strategy_validation.runner import ValidationGateService

from strategy_candidate_golden.golden import (
    BACKTEST_HASH,
    CAND_VERSION,
    CV_HASH,
    EXPERIMENT_ID,
    STRATEGY_CODE,
    STRATEGY_HASH,
    fake_backtest,
    make_candidate_env,
)


def golden_pass_inject() -> dict[str, Any]:
    """全 Gate PASS 的最小 inject（不跑 Qlib）。"""
    return {
        "cv_status": "PASSED",
        "metrics": {
            "is_sharpe": 1.1,
            "oos_sharpe": 0.95,
            "net_sharpe": 0.9,
            "gross_sharpe": 1.05,
            "total_cost": 0.02,
            "max_drawdown": 0.12,
            "turnover": 1.5,
            "slippage_bps": 8.0,
            "realism": "NET",
        },
        "capacity": {"notional": 500_000.0, "participation_rate": 0.05},
        "stability_windows": [
            {"sharpe": 0.9},
            {"sharpe": 0.85},
            {"sharpe": 0.95},
        ],
        "pit_signals": [],
    }


def golden_pit_leak_inject() -> dict[str, Any]:
    """PIT 泄漏 → Gate FAILED。"""
    base = golden_pass_inject()
    base["pit_leak_ratio"] = 0.01
    base["feature_leakage"] = 0.0
    return base


def seed_cv_passed(registry: LocalJsonRegistry) -> None:
    """登记 cv_hash 对应 PASSED 摘要。"""
    registry.upsert_research_cross_validation(
        CrossValidationSummary(
            cv_hash=CV_HASH,
            strategy_hash=STRATEGY_HASH,
            backtest_hash=BACKTEST_HASH,
            status="PASSED",
        )
    )
    bt = fake_backtest()
    registry.upsert_research_backtest(
        bt.model_copy(
            update={
                "metrics_json": golden_pass_inject()["metrics"],
                "metadata": {**(bt.metadata or {}), "cv_status": "PASSED"},
            }
        )
    )


def make_validation_env(
    tmp: Path,
) -> tuple[ValidationGateService, StrategyCandidateService, StrategyRegistryService]:
    cand_svc, reg_svc, registry = make_candidate_env(tmp)
    seed_cv_passed(registry)
    val_svc = ValidationGateService(
        cand_svc._store,
        registry,
        candidate_service=cand_svc,
    )
    return val_svc, cand_svc, reg_svc


def validated_candidate(cand_svc: StrategyCandidateService) -> Any:
    """走完整 8B 状态机至 VALIDATED。"""
    cand = cand_svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
        cv_hash=CV_HASH,
    )
    cand_svc.generate(cand.candidate_id)
    cand_svc.start_evaluating(cand.candidate_id)
    cand_svc.mark_ready(cand.candidate_id)
    return cand_svc.mark_validated(cand.candidate_id, operator="golden")


__all__ = [
    "golden_pass_inject",
    "golden_pit_leak_inject",
    "make_validation_env",
    "seed_cv_passed",
    "validated_candidate",
]
