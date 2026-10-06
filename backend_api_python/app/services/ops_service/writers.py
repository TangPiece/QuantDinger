"""Ops → Registry + R2 明细。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.services.research_data.contracts import (
    OpsAlertEventSummary,
    OpsAlertRuleRecord,
    OpsAuditEventSummary,
    OpsHealthSnapshotRecord,
    OpsIncidentSummary,
    OpsSloDefinitionRecord,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import OpsArtifactStore
from .protocol import (
    ENGINE_VERSION,
    AlertEvent,
    AlertRule,
    AuditEvent,
    Incident,
    SLODefinition,
    TradingOpsSnapshot,
)


class OpsWriter:
    """审计只追加；health/alert/incident 可 upsert 索引。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: OpsArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or OpsArtifactStore()

    def audit_exists(self, event_id: str) -> bool:
        try:
            self._registry.get_ops_audit_event(event_id)
            return True
        except KeyError:
            return False

    def get_audit_event(self, event_id: str) -> AuditEvent:
        rec = self._registry.get_ops_audit_event(event_id)
        return _audit_from_summary(rec)

    def write_audit_event(self, event: AuditEvent) -> OpsAuditEventSummary:
        uri, cs = self._artifacts.write_audit_event(event)
        meta = dict(event.metadata or {})
        meta["before"] = dict(event.before or {})
        meta["after"] = dict(event.after or {})
        meta["storage_uri"] = uri
        meta["checksum"] = cs
        meta["engine_version"] = ENGINE_VERSION
        summary = OpsAuditEventSummary(
            event_id=event.event_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            actor_type=str(event.actor.actor_type),
            actor_id=event.actor.actor_id,
            trace_id=event.trace_id,
            account_id=event.account_id,
            strategy_id=event.strategy_id,
            order_id=event.order_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            reason=event.reason,
            metadata=meta,
        )
        self._registry.append_ops_audit_event(summary)
        return summary

    def list_audit_events(
        self,
        *,
        account_id: str = "",
        strategy_id: str = "",
        order_id: str = "",
        trace_id: str = "",
        event_type: str = "",
        limit: int = 200,
    ) -> list[AuditEvent]:
        rows = self._registry.list_ops_audit_events(
            account_id=account_id,
            strategy_id=strategy_id,
            order_id=order_id,
            trace_id=trace_id,
            event_type=event_type,
            limit=limit,
        )
        return [_audit_from_summary(r) for r in rows]

    def write_health_snapshot(self, snap: TradingOpsSnapshot) -> OpsHealthSnapshotRecord:
        rec = OpsHealthSnapshotRecord(
            snapshot_id=snap.snapshot_id,
            captured_at=snap.captured_at,
            overall_status=snap.health.overall,
            health_json=snap.health.model_dump(mode="json"),
            counters_json=dict(snap.counters or {}),
            engine_version=snap.engine_version,
            metadata=dict(snap.metadata or {}),
        )
        self._registry.upsert_ops_health_snapshot(rec)
        return rec

    def upsert_alert_rule(self, rule: AlertRule) -> OpsAlertRuleRecord:
        rec = OpsAlertRuleRecord(
            rule_id=rule.rule_id,
            enabled=bool(rule.enabled),
            metric_or_signal=rule.metric_or_signal,
            severity=str(rule.severity),
            threshold=float(rule.threshold),
            comparison=str(rule.comparison),
            description=rule.description,
            safety_source_kind=rule.safety_source_kind,
            metadata=dict(rule.metadata or {}),
        )
        self._registry.upsert_ops_alert_rule(rec)
        return rec

    def list_alert_rules(self) -> list[AlertRule]:
        rows = self._registry.list_ops_alert_rules()
        return [
            AlertRule(
                rule_id=r.rule_id,
                enabled=bool(r.enabled),
                metric_or_signal=r.metric_or_signal,
                severity=r.severity,  # type: ignore[arg-type]
                threshold=float(r.threshold),
                comparison=r.comparison,  # type: ignore[arg-type]
                description=r.description,
                safety_source_kind=r.safety_source_kind,
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]

    def write_alert_event(self, alert: AlertEvent) -> OpsAlertEventSummary:
        rec = OpsAlertEventSummary(
            alert_id=alert.alert_id,
            rule_id=alert.rule_id,
            severity=str(alert.severity),
            fired_at=alert.fired_at,
            message=alert.message,
            account_id=alert.account_id,
            strategy_id=alert.strategy_id,
            trace_id=alert.trace_id,
            incident_id=alert.incident_id,
            metadata=dict(alert.metadata or {}),
        )
        self._registry.upsert_ops_alert_event(rec)
        return rec

    def write_incident(self, incident: Incident) -> OpsIncidentSummary:
        uri, cs = self._artifacts.write_incident(incident)
        meta = dict(incident.metadata or {})
        meta["storage_uri"] = uri
        meta["checksum"] = cs
        rec = OpsIncidentSummary(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=str(incident.severity),
            status=str(incident.status),
            account_id=incident.account_id,
            strategy_id=incident.strategy_id,
            trace_id=incident.trace_id,
            opened_at=incident.opened_at,
            updated_at=incident.updated_at,
            resolved_at=incident.resolved_at,
            timeline_event_ids=list(incident.timeline_event_ids),
            alert_ids=list(incident.alert_ids),
            metadata=meta,
        )
        self._registry.upsert_ops_incident(rec)
        return rec

    def get_incident(self, incident_id: str) -> Incident:
        rec = self._registry.get_ops_incident(incident_id)
        return _incident_from_summary(rec)

    def upsert_slo(self, slo: SLODefinition) -> OpsSloDefinitionRecord:
        rec = OpsSloDefinitionRecord(
            slo_id=slo.slo_id,
            name=slo.name,
            target_ratio=float(slo.target_ratio),
            window_sec=float(slo.window_sec),
            metric_name=slo.metric_name,
            enabled=bool(slo.enabled),
            metadata=dict(slo.metadata or {}),
        )
        self._registry.upsert_ops_slo_definition(rec)
        return rec


def _audit_from_summary(rec: OpsAuditEventSummary) -> AuditEvent:
    from .protocol import AuditActor

    meta = dict(rec.metadata or {})
    before = dict(meta.pop("before", {}) or {})
    after = dict(meta.pop("after", {}) or {})
    return AuditEvent(
        event_id=rec.event_id,
        event_type=rec.event_type,
        timestamp=rec.timestamp,
        actor=AuditActor(actor_type=rec.actor_type, actor_id=rec.actor_id),  # type: ignore[arg-type]
        trace_id=rec.trace_id,
        account_id=rec.account_id,
        strategy_id=rec.strategy_id,
        order_id=rec.order_id,
        entity_type=rec.entity_type,
        entity_id=rec.entity_id,
        before=before,
        after=after,
        reason=rec.reason,
        metadata=meta,
    )


def _incident_from_summary(rec: OpsIncidentSummary) -> Incident:
    return Incident(
        incident_id=rec.incident_id,
        title=rec.title,
        severity=rec.severity,  # type: ignore[arg-type]
        status=rec.status,  # type: ignore[arg-type]
        account_id=rec.account_id,
        strategy_id=rec.strategy_id,
        trace_id=rec.trace_id,
        opened_at=rec.opened_at,
        updated_at=rec.updated_at,
        resolved_at=rec.resolved_at,
        timeline_event_ids=list(rec.timeline_event_ids or []),
        alert_ids=list(rec.alert_ids or []),
        metadata=dict(rec.metadata or {}),
    )
