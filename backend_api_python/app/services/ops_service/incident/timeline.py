"""Alert / Audit 聚合为 Incident 时间线。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from ..hash import derive_incident_id
from ..protocol import AlertEvent, AuditEvent, Incident


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_incident(
    *,
    alert: AlertEvent | None = None,
    account_id: str = "",
    trace_id: str = "",
    title: str = "",
    severity: str = "WARNING",
    salt: str = "",
) -> Incident:
    """由 CRITICAL/WARNING 告警打开 Incident。"""
    acct = account_id or (alert.account_id if alert else "")
    tid = trace_id or (alert.trace_id if alert else "")
    iid = derive_incident_id(account_id=acct, trace_id=tid, salt=salt or (alert.alert_id if alert else ""))
    now = _now()
    sev = str(alert.severity if alert else severity).upper()
    return Incident(
        incident_id=iid,
        title=title or (alert.message if alert else "incident"),
        severity=sev,  # type: ignore[arg-type]
        status="OPEN",
        account_id=acct,
        strategy_id=alert.strategy_id if alert else "",
        trace_id=tid,
        opened_at=now,
        updated_at=now,
        alert_ids=[alert.alert_id] if alert else [],
        metadata={"source": "alert" if alert else "manual"},
    )


def append_to_incident(
    incident: Incident,
    *,
    audit_event: AuditEvent | None = None,
    alert: AlertEvent | None = None,
) -> Incident:
    """追加 timeline 引用（不修改历史 audit）。"""
    ids = list(incident.timeline_event_ids)
    alerts = list(incident.alert_ids)
    if audit_event is not None and audit_event.event_id not in ids:
        ids.append(audit_event.event_id)
    if alert is not None and alert.alert_id not in alerts:
        alerts.append(alert.alert_id)
    sev = incident.severity
    if alert is not None and str(alert.severity) == "CRITICAL":
        sev = "CRITICAL"
    return incident.model_copy(
        update={
            "timeline_event_ids": ids,
            "alert_ids": alerts,
            "updated_at": _now(),
            "severity": sev,
        }
    )


def build_timeline(
    incident: Incident,
    audit_events: Sequence[AuditEvent],
    alerts: Sequence[AlertEvent],
) -> list[dict[str, Any]]:
    """合并排序的时间线视图（供 Dashboard / 测试）。"""
    items: list[dict[str, Any]] = []
    audit_by_id = {e.event_id: e for e in audit_events}
    for eid in incident.timeline_event_ids:
        ev = audit_by_id.get(eid)
        if ev:
            items.append(
                {
                    "kind": "audit",
                    "at": ev.timestamp,
                    "event_type": ev.event_type,
                    "event_id": ev.event_id,
                }
            )
    alert_by_id = {a.alert_id: a for a in alerts}
    for aid in incident.alert_ids:
        al = alert_by_id.get(aid)
        if al:
            items.append(
                {
                    "kind": "alert",
                    "at": al.fired_at,
                    "rule_id": al.rule_id,
                    "severity": al.severity,
                    "alert_id": al.alert_id,
                }
            )
    return sorted(items, key=lambda x: str(x.get("at") or ""))
