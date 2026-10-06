"""Ops Registry 端口（由 ResearchRegistry 实现）。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import (
    OpsAlertEventSummary,
    OpsAlertRuleRecord,
    OpsAuditEventSummary,
    OpsHealthSnapshotRecord,
    OpsIncidentSummary,
    OpsSloDefinitionRecord,
)


class OpsRepository(Protocol):
    def append_ops_audit_event(self, record: OpsAuditEventSummary) -> None: ...

    def get_ops_audit_event(self, event_id: str) -> OpsAuditEventSummary: ...

    def list_ops_audit_events(
        self,
        *,
        account_id: str = "",
        strategy_id: str = "",
        order_id: str = "",
        trace_id: str = "",
        event_type: str = "",
        limit: int = 200,
    ) -> list[OpsAuditEventSummary]: ...

    def upsert_ops_health_snapshot(
        self, record: OpsHealthSnapshotRecord
    ) -> None: ...

    def get_ops_health_snapshot(
        self, snapshot_id: str
    ) -> OpsHealthSnapshotRecord: ...

    def upsert_ops_alert_rule(self, record: OpsAlertRuleRecord) -> None: ...

    def list_ops_alert_rules(self) -> list[OpsAlertRuleRecord]: ...

    def upsert_ops_alert_event(self, record: OpsAlertEventSummary) -> None: ...

    def get_ops_alert_event(self, alert_id: str) -> OpsAlertEventSummary: ...

    def upsert_ops_incident(self, record: OpsIncidentSummary) -> None: ...

    def get_ops_incident(self, incident_id: str) -> OpsIncidentSummary: ...

    def upsert_ops_slo_definition(
        self, record: OpsSloDefinitionRecord
    ) -> None: ...

    def list_ops_slo_definitions(self) -> list[OpsSloDefinitionRecord]: ...
