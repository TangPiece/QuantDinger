"""OpsService：Monitoring / Audit / Alert 主入口。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.research_data.registry import ResearchRegistry

from .alert.safety_policy import default_alert_rules
from .artifact_store import OpsArtifactStore
from .audit.emit import AppendOnlyConflict, emit_audit
from .cycle import (
    audit_config_change,
    on_broker_disconnect,
    on_broker_recovery,
    record_order_metric,
    run_collect_health,
    run_evaluate_alerts,
)
from .incident.timeline import append_to_incident, build_timeline, open_incident
from .metrics.counters import MetricsRegistry
from .protocol import AlertRule, AuditActor, AuditEvent, SLODefinition
from .trace import get_trace
from .writers import OpsWriter


class OpsError(RuntimeError):
    """Ops 编排错误。"""


class OpsService:
    """Phase 6H：可观察性；不创建订单。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: OpsArtifactStore | None = None,
        safety_service: Any = None,
        broker_port: Any = None,
    ) -> None:
        self._registry = registry
        self._safety = safety_service
        self._broker = broker_port
        self._writer = OpsWriter(registry, artifact_store=artifact_store)
        self._metrics = MetricsRegistry()
        self._rules = self._load_rules()
        self._recon_critical_accounts: set[str] = set()

    @property
    def writer(self) -> OpsWriter:
        return self._writer

    @property
    def metrics(self) -> MetricsRegistry:
        return self._metrics

    def set_safety_service(self, safety_service: Any) -> None:
        self._safety = safety_service

    def set_broker_port(self, broker_port: Any) -> None:
        self._broker = broker_port

    def _load_rules(self) -> list[AlertRule]:
        rows = self._writer.list_alert_rules()
        return rows if rows else default_alert_rules()

    def seed_default_rules(self) -> None:
        """将默认规则写入 Registry（幂等 upsert）。"""
        for r in default_alert_rules():
            self._writer.upsert_alert_rule(r)
        self._rules = self._load_rules()

    def emit_audit(self, **kwargs: Any) -> AuditEvent:
        return emit_audit(self._writer, **kwargs)

    def list_audit_events(self, **kwargs: Any) -> list[AuditEvent]:
        return self._writer.list_audit_events(**kwargs)

    def get_trace(self, trace_id: str) -> list[AuditEvent]:
        return get_trace(self._writer, trace_id)

    def collect_health(
        self,
        account_id: str = "",
        *,
        inject: Mapping[str, Any] | None = None,
        salt: str = "",
    ):
        return run_collect_health(
            writer=self._writer,
            metrics=self._metrics,
            account_id=account_id,
            broker_port=self._broker,
            safety_service=self._safety,
            recon_critical=account_id in self._recon_critical_accounts,
            inject=inject,
            salt=salt,
        )

    def evaluate_alerts(
        self,
        signals: Mapping[str, float],
        *,
        account_id: str = "",
        strategy_id: str = "",
        trace_id: str = "",
    ):
        return run_evaluate_alerts(
            writer=self._writer,
            rules=self._rules,
            signals=signals,
            safety_service=self._safety,
            account_id=account_id,
            strategy_id=strategy_id,
            trace_id=trace_id,
        )

    def audit_config_change(self, **kwargs: Any):
        return audit_config_change(self._writer, **kwargs)

    def record_order_metric(self, name: str, **kwargs: Any) -> None:
        record_order_metric(self._metrics, name, **kwargs)

    def notify_reconciliation_critical(
        self,
        account_id: str,
        *,
        run_id: str = "",
        finding_count: int = 0,
        trace_id: str = "",
    ) -> None:
        """6F CRITICAL：审计 + 告警 + Safety Policy。"""
        self._recon_critical_accounts.add(account_id)
        emit_audit(
            self._writer,
            event_type="RECONCILIATION_MISMATCH",
            actor=AuditActor(actor_type="SYSTEM", actor_id="reconciliation"),
            account_id=account_id,
            trace_id=trace_id,
            reason=f"critical findings n={finding_count}",
            metadata={"run_id": run_id},
            salt=run_id or account_id,
        )
        self.evaluate_alerts(
            {"reconciliation_critical": float(max(finding_count, 1))},
            account_id=account_id,
            trace_id=trace_id,
        )

    def notify_safety_block(
        self,
        account_id: str,
        *,
        reason: str = "",
        strategy_id: str = "",
        trace_id: str = "",
    ) -> AuditEvent:
        ev = emit_audit(
            self._writer,
            event_type="SAFETY_BLOCK",
            actor=AuditActor(actor_type="SYSTEM", actor_id="safety_gate"),
            account_id=account_id,
            strategy_id=strategy_id,
            trace_id=trace_id,
            reason=reason,
            salt=trace_id or account_id,
        )
        self.record_order_metric(
            "safety_block_total",
            account=account_id,
            strategy=strategy_id,
        )
        return ev

    def audit_kill_switch(
        self,
        *,
        engaged: bool,
        scope: str,
        scope_id: str,
        operator: str = "",
        reason: str = "",
    ) -> AuditEvent:
        """Kill Switch 开/关；记录 OPERATOR actor。"""
        et = "KILL_SWITCH_ON" if engaged else "KILL_SWITCH_OFF"
        return emit_audit(
            self._writer,
            event_type=et,
            actor=AuditActor(actor_type="OPERATOR", actor_id=operator or "system"),
            account_id=scope_id if scope == "ACCOUNT" else "",
            reason=reason,
            after={"scope": scope, "scope_id": scope_id, "engaged": engaged},
            salt=f"{scope}|{scope_id}|{et}",
        )

    def audit_safety_resume(
        self,
        *,
        scope: str,
        scope_id: str,
        operator: str = "",
    ) -> AuditEvent:
        return emit_audit(
            self._writer,
            event_type="SAFETY_RESUME",
            actor=AuditActor(actor_type="OPERATOR", actor_id=operator),
            account_id=scope_id if scope == "ACCOUNT" else "",
            after={"scope": scope, "scope_id": scope_id, "state": "NORMAL"},
            salt=f"{scope}|{scope_id}|resume",
        )

    def audit_safety_acknowledge(
        self,
        *,
        target: str,
        operator: str = "",
    ) -> AuditEvent:
        return emit_audit(
            self._writer,
            event_type="SAFETY_ACKNOWLEDGE",
            actor=AuditActor(actor_type="OPERATOR", actor_id=operator),
            entity_id=target,
            reason="acknowledged",
            salt=target,
        )

    def report_broker_disconnect(self, *, account_id: str = "", broker_id: str = "") -> None:
        on_broker_disconnect(
            self._writer, account_id=account_id, broker_id=broker_id
        )
        if self._broker is not None and hasattr(self._broker, "set_connected"):
            self._broker.set_connected(False)

    def report_broker_recovery(self, *, account_id: str = "", broker_id: str = "") -> None:
        on_broker_recovery(
            self._writer, account_id=account_id, broker_id=broker_id
        )
        if self._broker is not None and hasattr(self._broker, "set_connected"):
            self._broker.set_connected(True)

    def open_incident_for_alert(self, alert):
        inc = open_incident(alert=alert)
        self._writer.write_incident(inc)
        return inc

    def incident_timeline(self, incident_id: str) -> list[dict]:
        inc = self._writer.get_incident(incident_id)
        audits = self._writer.list_audit_events(trace_id=inc.trace_id, limit=500)
        return build_timeline(inc, audits, [])

    def upsert_slo(self, slo: SLODefinition):
        return self._writer.upsert_slo(slo)


__all__ = ["AppendOnlyConflict", "OpsError", "OpsService"]
