"""Phase 8D Golden：Fake inject + Promotion 脚手架。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.strategy_candidate.runner import StrategyCandidateService
from app.services.strategy_promotion.runner import StrategyPromotionService
from app.services.strategy_registry.runner import StrategyRegistryService
from app.services.strategy_validation.runner import ValidationGateService
from app.services.trading_governance.runner import TradingGovernanceService

from strategy_candidate_golden.golden import REGISTRY_VERSION, STRATEGY_CODE
from validation_gate_golden.golden import (
    golden_pass_inject,
    make_validation_env,
    validated_candidate,
)


def golden_promotion_metrics_inject() -> dict[str, Any]:
    """满足 Shadow/CL/LIVE policy 门槛（CI Fake）。"""
    return {
        "shadow_days": 5.0,
        "shadow_drawdown": 0.05,
        "shadow_drift": 0.01,
        "recon_errors": 0,
        "controlled_days": 3.0,
        "live_drawdown": 0.04,
        "slippage": 0.01,
        "reject_rate": 0.02,
        "risk_breach": 0,
    }


def seed_promoted_registry(
    cand_svc: StrategyCandidateService,
    reg_svc: StrategyRegistryService,
    val_svc: ValidationGateService,
    *,
    governance: TradingGovernanceService | None = None,
) -> tuple[Any, Any, str]:
    """VALIDATED + PASSED + promote_to_registry。"""
    cand = validated_candidate(cand_svc)
    run = val_svc.run(cand.candidate_id, inject=golden_pass_inject(), operator="golden")
    assert run.status == "PASSED"
    _, _, ver = cand_svc.promote_to_registry(
        cand.candidate_id,
        target_strategy_version=REGISTRY_VERSION,
    )
    reg_svc._governance = governance
    if governance is not None:
        reg_svc.link_governance_active(STRATEGY_CODE, REGISTRY_VERSION)
    return cand, ver, run.validation_id


def make_promotion_env(
    tmp: Path,
) -> tuple[
    StrategyPromotionService,
    StrategyCandidateService,
    StrategyRegistryService,
    ValidationGateService,
    TradingGovernanceService,
]:
    store = LocalCanonicalStore(root=tmp / "canonical")
    val_svc, cand_svc, reg_svc = make_validation_env(tmp)
    gov = TradingGovernanceService(store, cand_svc._registry)
    reg_svc._governance = gov
    promo = StrategyPromotionService(
        store,
        cand_svc._registry,
        strategy_registry=reg_svc,
        candidate_service=cand_svc,
        validation_service=val_svc,
        governance=gov,
        writer=None,
    )
    promo._writer._artifacts.root = tmp / "artifacts"
    return promo, cand_svc, reg_svc, val_svc, gov


__all__ = [
    "golden_promotion_metrics_inject",
    "make_promotion_env",
    "seed_promoted_registry",
]
