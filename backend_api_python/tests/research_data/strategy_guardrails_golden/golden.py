"""Phase 8G Golden：Fake inject + Strategy Guardrails 脚手架。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.strategy_guardrails.runner import StrategyGuardrailsService

from strategy_monitoring_golden.golden import (
    STRATEGY_CODE,
    golden_healthy_monitor_inject,
    make_monitoring_env,
    seed_feedback_comparison,
)


class FakeSafetyService:
    """记录 Safety Stop（无 flatten / 无 submit_order）。"""

    def __init__(self) -> None:
        self.halts: list[dict[str, str]] = []

    def kill_strategy(self, account_id: str, *, strategy_id: str, reason: str = "") -> None:
        self.halts.append(
            {
                "account_id": str(account_id),
                "strategy_id": str(strategy_id),
                "reason": str(reason),
            }
        )


class FakeGovernanceAdapter:
    """记录 throttle / pause（不 scale-up、不 reallocate capital）。"""

    def __init__(self) -> None:
        self._runtime_throttle_log: list[dict[str, Any]] = []
        self._runtime_pause_log: list[dict[str, Any]] = []


def golden_slippage_critical_guardrail_inject() -> dict[str, Any]:
    return {
        "guardrails": {
            "lifecycle_phase": "LIVE",
            "breaches": [
                {
                    "category": "EXECUTION",
                    "severity": "CRITICAL",
                    "metric": "slippage_bps",
                    "value": 45.0,
                    "message": "slippage critical",
                }
            ],
        }
    }


def golden_recon_emergency_guardrail_inject() -> dict[str, Any]:
    return {
        "guardrails": {
            "lifecycle_phase": "LIVE",
            "account_id": "acct_golden",
            "breaches": [
                {
                    "category": "RECONCILIATION",
                    "severity": "EMERGENCY",
                    "message": "recon emergency",
                }
            ],
        }
    }


def golden_performance_critical_guardrail_inject() -> dict[str, Any]:
    return {
        "guardrails": {
            "lifecycle_phase": "LIVE",
            "breaches": [
                {
                    "category": "PERFORMANCE",
                    "severity": "CRITICAL",
                    "metric": "shadow_drift",
                    "value": 0.22,
                }
            ],
        }
    }


def golden_risk_pause_guardrail_inject() -> dict[str, Any]:
    return {
        "guardrails": {
            "lifecycle_phase": "LIVE",
            "breaches": [
                {
                    "category": "RISK",
                    "severity": "CRITICAL",
                    "metric": "gross_exposure_util",
                    "value": 1.1,
                }
            ],
        }
    }


def make_guardrails_env(
    tmp: Path,
) -> tuple[
    StrategyGuardrailsService,
    Any,
    Any,
    Any,
    Any,
    FakeSafetyService,
    FakeGovernanceAdapter,
]:
    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(tmp)
    safety = FakeSafetyService()
    gov = FakeGovernanceAdapter()
    gr = StrategyGuardrailsService(
        mon._store,
        cand_svc._registry,
        monitoring=mon,
        governance=gov,
        safety=safety,
    )
    art_root = tmp / "artifacts"
    gr._writer._artifacts.root = art_root
    mon._writer._artifacts.root = art_root
    return gr, mon, fb, promo, cand_svc, reg_svc, val_svc, safety, gov


def seed_guardrails_baseline(
    mon: Any,
    fb: Any,
    promo: Any,
    cand_svc: Any,
    reg_svc: Any,
    val_svc: Any,
    *,
    idempotency_key: str = "gr_fb",
) -> None:
    seed_feedback_comparison(
        fb, promo, cand_svc, reg_svc, val_svc, idempotency_key=idempotency_key
    )
    mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_healthy_monitor_inject(), session_id="gr_seed"
    )


__all__ = [
    "FakeGovernanceAdapter",
    "FakeSafetyService",
    "STRATEGY_CODE",
    "golden_performance_critical_guardrail_inject",
    "golden_recon_emergency_guardrail_inject",
    "golden_risk_pause_guardrail_inject",
    "golden_slippage_critical_guardrail_inject",
    "make_guardrails_env",
    "seed_guardrails_baseline",
]
