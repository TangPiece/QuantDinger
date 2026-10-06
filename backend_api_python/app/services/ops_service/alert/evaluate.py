"""AlertRule + 信号 → AlertEvent。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ..hash import derive_alert_id
from ..protocol import AlertEvent, AlertRule


def _compare(value: float, threshold: float, op: str) -> bool:
    op = str(op).upper()
    if op == "GT":
        return value > threshold
    if op == "GTE":
        return value >= threshold
    if op == "LT":
        return value < threshold
    if op == "LTE":
        return value <= threshold
    if op == "EQ":
        return value == threshold
    return False


def evaluate_rules(
    rules: list[AlertRule],
    signals: Mapping[str, float],
    *,
    account_id: str = "",
    strategy_id: str = "",
    trace_id: str = "",
    salt: str = "",
) -> list[AlertEvent]:
    """对启用的规则评估 signals（metric_or_signal 为 key）。"""
    now = datetime.now(timezone.utc).isoformat()
    out: list[AlertEvent] = []
    for rule in rules:
        if not rule.enabled:
            continue
        key = str(rule.metric_or_signal or rule.rule_id)
        if key not in signals:
            continue
        val = float(signals[key])
        if not _compare(val, float(rule.threshold), rule.comparison):
            continue
        aid = derive_alert_id(rule_id=rule.rule_id, bucket=f"{account_id}|{trace_id}", salt=salt)
        out.append(
            AlertEvent(
                alert_id=aid,
                rule_id=rule.rule_id,
                severity=rule.severity,
                fired_at=now,
                message=rule.description or f"{rule.rule_id} fired",
                account_id=account_id,
                strategy_id=strategy_id,
                trace_id=trace_id,
                metadata={"signal_value": val, "threshold": rule.threshold},
            )
        )
    return out


def attach_incidents(
    writer: Any,
    alerts: list[AlertEvent],
    *,
    open_incident_fn: Any,
) -> list[AlertEvent]:
    """为告警打开/关联 Incident。"""
    updated: list[AlertEvent] = []
    for a in alerts:
        inc = open_incident_fn(a)
        updated.append(
            a.model_copy(update={"incident_id": inc.incident_id})
        )
        writer.write_alert_event(updated[-1])
    return updated
