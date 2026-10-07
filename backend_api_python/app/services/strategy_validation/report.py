"""Phase 8C：聚合各 Gate → ValidationResult / Run status。"""

from __future__ import annotations

from . import gates
from .bridge_from_candidate import ValidationEvidenceContext
from .protocol import (
    GateCheckResult,
    OverallValidationStatus,
    ValidationPolicyRules,
    ValidationResult,
    ValidationRunStatus,
)


def _skip_result(check: str) -> GateCheckResult:
    return GateCheckResult(check=check, status="SKIP", reason="not executed")


def build_validation_result(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> ValidationResult:
    """顺序执行 P0 Gate 并汇总 overall_status。"""
    lineage = gates.run_lineage_check(ctx, policy)
    leakage = gates.run_leakage_check(ctx, policy)
    pit = gates.run_pit_check(ctx, policy)
    cv = gates.run_cv_check(ctx, policy)
    oos = gates.run_oos_check(ctx, policy)
    overfit = gates.run_overfit_check(ctx, policy)
    cost = gates.run_cost_check(ctx, policy)
    capacity = gates.run_capacity_check(ctx, policy)
    risk = gates.run_risk_check(ctx, policy)
    stability = gates.run_stability_check(ctx, policy)

    hard_checks = [lineage, leakage, pit, cv, oos, overfit, cost, risk, stability]
    overall = _overall_status(hard_checks, capacity, policy)
    return ValidationResult(
        overall_status=overall,
        lineage_check=lineage,
        leakage_check=leakage,
        pit_check=pit,
        oos_check=oos,
        overfit_check=overfit,
        cost_check=cost,
        capacity_check=capacity,
        risk_check=risk,
        stability_check=stability,
    )


def _overall_status(
    checks: list[GateCheckResult],
    capacity: GateCheckResult,
    policy: ValidationPolicyRules,
) -> OverallValidationStatus:
    """FAIL 优先；容量边界可 CONDITIONAL（默认不可 promote）。"""
    for c in checks:
        if c.status == "FAIL":
            return "FAILED"
    if capacity.status == "FAIL":
        if policy.capacity_soft_fail:
            return "CONDITIONAL"
        return "FAILED"
    return "PASSED"


def run_status_from_result(result: ValidationResult) -> ValidationRunStatus:
    """ValidationRun.status 与 overall_status 对齐（无 VALIDATING）。"""
    mapping: dict[str, ValidationRunStatus] = {
        "PASSED": "PASSED",
        "FAILED": "FAILED",
        "CONDITIONAL": "CONDITIONAL",
    }
    return mapping.get(result.overall_status, "FAILED")


def empty_result() -> ValidationResult:
    """占位（不应出现在 completed run）。"""
    sk = _skip_result
    return ValidationResult(
        overall_status="FAILED",
        lineage_check=sk("lineage"),
        leakage_check=sk("leakage"),
        pit_check=sk("pit"),
        oos_check=sk("oos"),
        overfit_check=sk("overfit"),
        cost_check=sk("cost"),
        capacity_check=sk("capacity"),
        risk_check=sk("risk"),
        stability_check=sk("stability"),
    )


__all__ = ["build_validation_result", "empty_result", "run_status_from_result"]
