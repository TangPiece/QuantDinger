"""Safety state / event / kill_switch / rule → Registry。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.services.research_data.contracts import (
    KillSwitchRecord,
    SafetyEventSummary,
    SafetyRuleRecord,
    SafetyStateRecord,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import SafetyArtifactStore
from .protocol import (
    ENGINE_VERSION,
    KillSwitch,
    SafetyEvent,
    SafetyRule,
    SafetyState,
)


class SafetyWriter:
    """热路径状态走 Registry；事件明细可落 R2。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: SafetyArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or SafetyArtifactStore()

    def set_state(self, state: SafetyState) -> SafetyStateRecord:
        rec = SafetyStateRecord(
            scope=str(state.scope),
            scope_id=state.scope_id,
            state=str(state.state),
            acknowledged=bool(state.acknowledged),
            reason=state.reason,
            updated_at=state.updated_at
            or datetime.now(timezone.utc).isoformat(),
            metadata=dict(state.metadata or {}),
        )
        self._registry.set_safety_state(rec)
        return rec

    def get_state(self, scope: str, scope_id: str) -> SafetyState:
        rec = self._registry.get_safety_state(scope, scope_id)
        return SafetyState(
            scope=rec.scope,  # type: ignore[arg-type]
            scope_id=rec.scope_id,
            state=rec.state,  # type: ignore[arg-type]
            acknowledged=bool(rec.acknowledged),
            reason=rec.reason,
            updated_at=rec.updated_at,
            metadata=dict(rec.metadata or {}),
        )

    def set_kill_switch(self, ks: KillSwitch) -> KillSwitchRecord:
        rec = KillSwitchRecord(
            scope=str(ks.scope),
            scope_id=ks.scope_id,
            engaged=bool(ks.engaged),
            reason=ks.reason,
            engaged_at=ks.engaged_at,
            engaged_by=ks.engaged_by,
            metadata=dict(ks.metadata or {}),
        )
        self._registry.set_kill_switch(rec)
        return rec

    def get_kill_switch(self, scope: str, scope_id: str) -> KillSwitch:
        rec = self._registry.get_kill_switch(scope, scope_id)
        return KillSwitch(
            scope=rec.scope,  # type: ignore[arg-type]
            scope_id=rec.scope_id,
            engaged=bool(rec.engaged),
            reason=rec.reason,
            engaged_at=rec.engaged_at,
            engaged_by=rec.engaged_by,
            metadata=dict(rec.metadata or {}),
        )

    def upsert_rule(self, rule: SafetyRule) -> SafetyRuleRecord:
        rec = SafetyRuleRecord(
            rule_id=rule.rule_id,
            enabled=bool(rule.enabled),
            threshold=float(rule.threshold),
            action=str(rule.action),
            scope=str(rule.scope),
            metadata=dict(rule.metadata or {}),
        )
        self._registry.upsert_safety_rule(rec)
        return rec

    def write_event(self, event: SafetyEvent) -> SafetyEventSummary:
        uri, cs = self._artifacts.write_event(event)
        meta = dict(event.metadata or {})
        meta["storage_uri"] = uri
        meta["checksum"] = cs
        meta["engine_version"] = ENGINE_VERSION
        summary = SafetyEventSummary(
            event_id=event.event_id,
            scope=str(event.scope),
            scope_id=event.scope_id,
            rule=event.rule,
            severity=event.severity,
            state_before=event.state_before,
            state_after=event.state_after,
            reason=event.reason,
            trigger_value=float(event.trigger_value),
            threshold=float(event.threshold),
            created_at=event.created_at,
            resolved_at=event.resolved_at,
            operator=event.operator,
            acknowledged=bool(event.acknowledged),
            metadata=meta,
        )
        self._registry.upsert_safety_event(summary)
        return summary

    def get_event(self, event_id: str) -> SafetyEvent:
        rec = self._registry.get_safety_event(event_id)
        return SafetyEvent(
            event_id=rec.event_id,
            scope=rec.scope,  # type: ignore[arg-type]
            scope_id=rec.scope_id,
            rule=rec.rule,
            severity=rec.severity,
            state_before=rec.state_before,
            state_after=rec.state_after,
            reason=rec.reason,
            trigger_value=float(rec.trigger_value),
            threshold=float(rec.threshold),
            created_at=rec.created_at,
            resolved_at=rec.resolved_at,
            operator=rec.operator,
            acknowledged=bool(rec.acknowledged),
            metadata=dict(rec.metadata or {}),
        )

    def list_events(
        self, *, scope: str = "", scope_id: str = "", rule: str = ""
    ) -> list[SafetyEvent]:
        rows = self._registry.list_safety_events(
            scope=scope, scope_id=scope_id, rule=rule
        )
        return [
            SafetyEvent(
                event_id=r.event_id,
                scope=r.scope,  # type: ignore[arg-type]
                scope_id=r.scope_id,
                rule=r.rule,
                severity=r.severity,
                state_before=r.state_before,
                state_after=r.state_after,
                reason=r.reason,
                trigger_value=float(r.trigger_value),
                threshold=float(r.threshold),
                created_at=r.created_at,
                resolved_at=r.resolved_at,
                operator=r.operator,
                acknowledged=bool(r.acknowledged),
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]

    def event_exists(self, event_id: str) -> bool:
        try:
            self._registry.get_safety_event(event_id)
            return True
        except KeyError:
            return False
