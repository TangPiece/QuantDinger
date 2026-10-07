"""Phase 8G：GovernanceIncident 构造与 FSM 推进。"""

from __future__ import annotations

from datetime import datetime, timezone

from .fsm import InvalidGuardrailTransitionError, assert_incident_transition
from .identity import build_incident_id
from .protocol import BreachSignal, GovernanceIncident, GuardrailActionType


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_incident(
    *,
    strategy_code: str,
    breach: BreachSignal,
    recommended_action: GuardrailActionType,
    session_id: str = "",
    requires_decision: bool = False,
) -> GovernanceIncident:
    ts = _now()
    status = "REVIEW_REQUIRED" if recommended_action == "REVIEW" or requires_decision else "OPEN"
    return GovernanceIncident(
        incident_id=build_incident_id(
            strategy_code=strategy_code,
            category=breach.category,
            opened_at=ts,
        ),
        strategy_code=strategy_code,
        status=status,  # type: ignore[arg-type]
        severity=str(breach.severity or "CRITICAL").upper(),
        category=str(breach.category or "SYSTEM").upper(),
        recommended_action=recommended_action,
        alert_id=breach.alert_id or "",
        message=breach.message or f"{breach.category} {breach.severity} breach",
        requires_decision=requires_decision or recommended_action in ("STOP", "ROLLBACK"),
        opened_at=ts,
        session_id=session_id,
    )


def transition_incident(incident: GovernanceIncident, target: str) -> GovernanceIncident:
    try:
        assert_incident_transition(incident.status, target)  # type: ignore[arg-type]
    except InvalidGuardrailTransitionError:
        raise
    updates: dict[str, object] = {"status": target}
    if target == "RESOLVED":
        updates["resolved_at"] = _now()
    return incident.model_copy(update=updates)


__all__ = ["open_incident", "transition_incident"]
