"""Phase 8G：GovernanceDecision 构造与审批校验。"""

from __future__ import annotations

from datetime import datetime, timezone

from .identity import build_decision_id
from .protocol import DecisionStatus, DecisionType, GovernanceDecision


class GuardrailDecisionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_decision(
    *,
    strategy_code: str,
    decision_type: DecisionType,
    operator: str = "",
    reason: str = "",
    incident_id: str = "",
    to_version: str = "",
    session_id: str = "",
    status: DecisionStatus = "PENDING",
) -> GovernanceDecision:
    ts = _now()
    return GovernanceDecision(
        decision_id=build_decision_id(
            strategy_code=strategy_code,
            decision_type=decision_type,
            submitted_at=ts,
        ),
        strategy_code=strategy_code,
        incident_id=incident_id,
        decision_type=decision_type,
        status=status,
        operator=operator,
        reason=reason,
        to_version=to_version,
        submitted_at=ts,
        session_id=session_id,
    )


def approve_decision(decision: GovernanceDecision, *, operator: str) -> GovernanceDecision:
    if decision.status not in ("PENDING",):
        raise GuardrailDecisionError(f"decision not pending: {decision.status}")
    ts = _now()
    return decision.model_copy(
        update={
            "status": "APPROVED",
            "operator": operator or decision.operator,
            "approved_at": ts,
        }
    )


def assert_executable(decision: GovernanceDecision) -> None:
    if decision.status != "APPROVED":
        raise GuardrailDecisionError("approved decision required")


__all__ = [
    "GuardrailDecisionError",
    "approve_decision",
    "assert_executable",
    "new_decision",
]
