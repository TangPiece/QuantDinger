"""RiskSnapshot / DecisionEvent 构建。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from .hash import compute_event_id
from .protocol import (
    RiskContext,
    RiskDecision,
    RiskDecisionEvent,
    RiskSnapshot,
)


def build_snapshot(
    *,
    risk_run_id: str,
    context: RiskContext,
    decision: RiskDecision,
    storage_uri: str = "",
) -> RiskSnapshot:
    max_pos = 0.0
    for d in decision.adjusted_deltas or context.deltas:
        max_pos = max(max_pos, abs(float(d.target_weight)))
    turnover = 0.5 * sum(
        abs(float(d.delta_weight)) for d in (decision.adjusted_deltas or context.deltas)
    )
    cash = float(context.account.cash.available_cash) if context.account else 0.0
    return RiskSnapshot(
        risk_run_id=risk_run_id,
        account_id=context.account_id,
        portfolio_id=context.portfolio_id,
        apply_id=context.apply_id,
        runtime_id=context.runtime_id,
        bundle_hash=context.bundle_hash,
        policy_hash=context.policy.policy_hash,
        trading_date=context.trading_date,
        timestamp=datetime.now(timezone.utc).isoformat(),
        gross_exposure=float(context.exposure.gross_exposure),
        net_exposure=float(context.exposure.net_exposure),
        max_position=max_pos,
        turnover=turnover,
        available_cash=cash,
        risk_status=decision.verdict,
        storage_uri=storage_uri,
        metadata={"n_results": len(decision.results)},
    )


def build_events(
    *,
    risk_run_id: str,
    decision: RiskDecision,
) -> list[RiskDecisionEvent]:
    now = datetime.now(timezone.utc).isoformat()
    events: list[RiskDecisionEvent] = []
    # 总决策事件
    events.append(
        RiskDecisionEvent(
            event_id=compute_event_id(risk_run_id, "DECISION", salt=decision.verdict),
            risk_run_id=risk_run_id,
            rule_code="DECISION",
            decision=decision.verdict,
            message=decision.message,
            created_at=now,
        )
    )
    for i, r in enumerate(decision.results):
        if r.decision == "ALLOW":
            continue
        events.append(
            RiskDecisionEvent(
                event_id=compute_event_id(
                    risk_run_id, r.rule_code, salt=f"{r.instrument_key}|{i}"
                ),
                risk_run_id=risk_run_id,
                rule_code=r.rule_code,
                decision=r.decision,
                severity=r.severity,
                instrument_key=r.instrument_key,
                message=r.message,
                original_value=r.original_value,
                limit_value=r.limit_value,
                payload=dict(r.metadata or {}),
                created_at=now,
            )
        )
    return events
