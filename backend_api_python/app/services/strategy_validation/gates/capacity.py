"""Phase 8C：容量 Gate（只读 7E check_capacity 预检）。"""

from __future__ import annotations

from app.services.trading_governance.capacity import check_capacity
from app.services.trading_governance.protocol import CapacityLimit, OrderRiskContext

from ..bridge_from_candidate import ValidationEvidenceContext
from ..protocol import GateCheckResult, ValidationPolicyRules


def run_capacity_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    cap_data = ctx.capacity_ctx
    notional = float(cap_data.get("notional") or cap_data.get("order_notional") or 0.0)
    participation = float(cap_data.get("participation_rate") or 0.0)
    if notional <= 0 and participation <= 0:
        return GateCheckResult(
            check="capacity",
            status="SKIP",
            reason="no capacity inject; skipped",
        )
    # min_capacity_notional：期望策略可承载的最小名义规模
    if policy.min_capacity_notional > 0 and notional < policy.min_capacity_notional:
        return GateCheckResult(
            check="capacity",
            status="FAIL",
            reason="notional below min_capacity_notional",
            metrics={"notional": notional, "min": policy.min_capacity_notional},
        )
    risk_ctx = OrderRiskContext(
        account_id="validation_gate",
        strategy_id=str(cap_data.get("strategy_id") or "validation_gate"),
        quantity=float(cap_data.get("quantity") or 1.0),
        notional=notional or 1.0,
        metadata={"participation_rate": participation} if participation else {},
    )
    ok, reason = check_capacity(
        CapacityLimit(
            strategy_id=str(cap_data.get("strategy_id") or "validation_gate"),
            max_notional=0.0,
            max_participation_rate=policy.max_participation_rate,
        ),
        risk_ctx,
    )
    if not ok:
        return GateCheckResult(
            check="capacity",
            status="FAIL",
            reason=reason or "capacity check failed",
            metrics={"participation_rate": participation, "notional": notional},
        )
    return GateCheckResult(
        check="capacity",
        status="PASS",
        metrics={"notional": notional, "participation_rate": participation},
    )


__all__ = ["run_capacity_check"]
