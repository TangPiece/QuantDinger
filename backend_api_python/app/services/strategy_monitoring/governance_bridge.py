"""Phase 8F：GovernanceBridge — 仅 REVIEW_REQUIRED 事件。"""

from __future__ import annotations

from datetime import datetime, timezone

from .identity import build_governance_event_id
from .protocol import AlertSeverity, GovernanceReviewEvent, MetricCategory, StrategyAlert


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_HARD_GOV_CATEGORIES: frozenset[MetricCategory] = frozenset(
    {"RECONCILIATION", "RISK", "MARKET_DATA"}
)


def should_emit_governance(alert: StrategyAlert) -> bool:
    if alert.severity in ("CRITICAL", "EMERGENCY"):
        return True
    return alert.category in _HARD_GOV_CATEGORIES and alert.severity == "WARNING"


def build_review_event(
    alert: StrategyAlert,
    *,
    session_id: str = "",
) -> GovernanceReviewEvent:
    ts = _now()
    return GovernanceReviewEvent(
        event_id=build_governance_event_id(
            strategy_code=alert.strategy_code,
            alert_id=alert.alert_id,
            created_at=ts,
        ),
        strategy_code=alert.strategy_code,
        event_type="REVIEW_REQUIRED",
        severity=alert.severity,
        category=alert.category,
        alert_id=alert.alert_id,
        message=f"策略监控复核：{alert.title} — {alert.message}",
        created_at=ts,
        session_id=session_id or alert.session_id,
        metadata={"occurrence_count": alert.occurrence_count},
    )


__all__ = ["build_review_event", "should_emit_governance"]
