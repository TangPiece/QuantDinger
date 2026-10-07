"""Phase 8F：StrategyMonitoringService 门面（只观察，无自动降级 / OMS）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .alert_engine import evaluate_rules, merge_alert
from .bridges.bridge_from_feedback import load_feedback_scalars
from .bridges.reconciliation import load_reconciliation_inject
from .bridges.risk_policy import load_risk_limits
from .collectors import collect_all_metrics
from .collectors.metrics_inject import merge_inject_sections
from .dashboard import build_dashboard_snapshot
from .fsm import InvalidAlertTransitionError, assert_alert_transition
from .governance_bridge import build_review_event, should_emit_governance
from .health import build_strategy_health
from .identity import build_health_snapshot_id, normalize_session_id
from .notification import NotificationDispatcher
from .policy import resolve_monitor_policy
from .protocol import (
    DashboardSnapshot,
    GovernanceReviewEvent,
    MonitoringMetric,
    NotificationDispatch,
    StrategyAlert,
    StrategyHealth,
)
from .writers import StrategyMonitoringWriter


class StrategyMonitoringError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrategyMonitoringService:
    """Monitoring Engine：collect → health → alert → notify / governance。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        feedback: Any | None = None,
        risk: Any | None = None,
        reconciliation: Any | None = None,
        writer: StrategyMonitoringWriter | None = None,
        notifier: NotificationDispatcher | None = None,
        guardrails: Any | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._feedback = feedback
        self._risk = risk
        self._reconciliation = reconciliation
        self._writer = writer or StrategyMonitoringWriter(registry)
        self._notifier = notifier or NotificationDispatcher()
        self._guardrails = guardrails
        self._latest_health: dict[str, StrategyHealth] = {}

    def _try_evaluate_guardrails(self, strategy_code: str, *, inject: Any = None) -> None:
        """8G 可选：监控成功后评估 Guardrail（失败不回滚监控）。"""
        if self._guardrails is None:
            return
        try:
            self._guardrails.evaluate_from_monitoring(
                strategy_code, inject=inject, session_id=""
            )
        except Exception:
            pass

    def collect_and_evaluate(
        self,
        strategy_code: str,
        *,
        inject: Mapping[str, Any] | None = None,
        session_id: str = "",
    ) -> StrategyHealth:
        code = str(strategy_code or "").strip()
        if not code:
            raise StrategyMonitoringError("strategy_code required")
        sid = normalize_session_id(session_id)
        ts = _now()

        policy = resolve_monitor_policy(self._registry)
        self._writer.write_policy(policy)

        fb_scalars = load_feedback_scalars(self._feedback, strategy_code=code)
        risk_limits = load_risk_limits(self._risk, strategy_code=code)
        sections = merge_inject_sections(inject)
        recon_inject = load_reconciliation_inject(
            self._reconciliation,
            strategy_code=code,
            inject_section=sections.get("reconciliation"),
        )

        metrics = collect_all_metrics(
            strategy_code=code,
            collected_at=ts,
            session_id=sid,
            policy=policy,
            inject=inject,
            feedback_scalars=fb_scalars,
            risk_limits=risk_limits,
            recon_inject=recon_inject,
        )
        for m in metrics:
            self._writer.write_metric(m)

        snap_id = build_health_snapshot_id(
            strategy_code=code, evaluated_at=ts, session_id=sid
        )
        health = build_strategy_health(
            snapshot_id=snap_id,
            strategy_code=code,
            metrics=metrics,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_content_hash=policy.policy_content_hash,
            evaluated_at=ts,
            session_id=sid,
        )
        health = self._writer.write_health(health)
        self._latest_health[code] = health

        triggers = evaluate_rules(
            strategy_code=code,
            policy=policy,
            metrics=metrics,
            session_id=sid,
        )
        for rule, sev, val, fp in triggers:
            existing = self._find_alert_by_dedup(code, rule.rule_id, fp)
            is_new = existing is None
            alert, notify = merge_alert(
                strategy_code=code,
                rule=rule,
                severity=sev,
                value=val,
                fingerprint=fp,
                existing=existing,
                session_id=sid,
            )
            self._writer.write_alert(alert)
            if notify:
                disp = self._notifier.dispatch(alert, session_id=sid)
                self._writer.write_notification(disp)
            if is_new and should_emit_governance(alert):
                gov = build_review_event(alert, session_id=sid)
                self._writer.write_governance_event(gov)

        self._try_evaluate_guardrails(code, inject=inject)
        return health

    def _find_alert_by_dedup(
        self, strategy_code: str, rule_id: str, fingerprint: str
    ) -> StrategyAlert | None:
        try:
            row = self._registry.get_strategy_alert_by_dedup(
                strategy_code=strategy_code,
                rule_id=rule_id,
                fingerprint=fingerprint,
            )
        except Exception:
            return None
        return self._alert_from_summary(row)

    def _alert_from_summary(self, row: Any) -> StrategyAlert:
        return StrategyAlert(
            alert_id=row.alert_id,
            strategy_code=row.strategy_code,
            rule_id=row.rule_id,
            fingerprint=row.fingerprint,
            category=row.category,  # type: ignore[arg-type]
            severity=row.severity,  # type: ignore[arg-type]
            status=row.status,  # type: ignore[arg-type]
            title=row.title,
            message=row.message,
            occurrence_count=int(row.occurrence_count),
            consecutive_critical_count=int(row.consecutive_critical_count),
            first_seen_at=row.first_seen_at or "",
            last_seen_at=row.last_seen_at or "",
            cooldown_until=row.cooldown_until or "",
            suppressed_until=row.suppressed_until or "",
            acknowledged_at=row.acknowledged_at or "",
            investigating_at=row.investigating_at or "",
            resolved_at=row.resolved_at or "",
            session_id=row.session_id or "",
            metadata=dict(row.metadata or {}),
        )

    def get_health(self, strategy_code: str) -> StrategyHealth:
        code = str(strategy_code or "").strip()
        if code in self._latest_health:
            return self._latest_health[code]
        rows = self._registry.list_strategy_health_snapshots(strategy_code=code)
        if not rows:
            raise StrategyMonitoringError(f"no health for {code}")
        latest = rows[-1]
        from .protocol import DimensionHealth

        return StrategyHealth(
            snapshot_id=latest.snapshot_id,
            strategy_code=latest.strategy_code,
            overall=latest.overall,  # type: ignore[arg-type]
            dimensions=[
                DimensionHealth.model_validate(d) for d in (latest.dimensions_json or [])
            ],
            policy_id=latest.policy_id,
            policy_version=latest.policy_version,
            policy_content_hash=latest.policy_content_hash,
            evaluated_at=latest.evaluated_at or "",
            session_id=latest.session_id or "",
            storage_uri=latest.storage_uri or "",
        )

    def list_metrics(
        self,
        strategy_code: str,
        *,
        category: str | None = None,
        limit: int = 200,
    ) -> list[MonitoringMetric]:
        rows = self._registry.list_strategy_monitor_metrics(strategy_code=strategy_code)
        out: list[MonitoringMetric] = []
        for row in rows:
            if category and str(row.category).upper() != str(category).upper():
                continue
            out.append(
                MonitoringMetric(
                    metric_id=row.metric_id,
                    strategy_code=row.strategy_code,
                    category=row.category,  # type: ignore[arg-type]
                    name=row.name,
                    value=float(row.value),
                    unit=row.unit or "",
                    health=row.health,  # type: ignore[arg-type]
                    window=row.window or "5m",
                    collected_at=row.collected_at or "",
                    session_id=row.session_id or "",
                    labels=dict(row.labels_json or {}),
                )
            )
        out.sort(key=lambda m: m.collected_at or "")
        if limit > 0:
            out = out[-limit:]
        return out

    def list_alerts(
        self,
        strategy_code: str,
        *,
        status: str | None = None,
    ) -> list[StrategyAlert]:
        rows = self._registry.list_strategy_alerts(strategy_code=strategy_code)
        out = [self._alert_from_summary(r) for r in rows]
        if status:
            st = str(status).upper()
            out = [a for a in out if a.status == st]
        out.sort(key=lambda a: a.last_seen_at or a.first_seen_at or "")
        return out

    def ack_alert(self, alert_id: str) -> StrategyAlert:
        return self._transition_alert(alert_id, "ACKNOWLEDGED", field="acknowledged_at")

    def investigate_alert(self, alert_id: str) -> StrategyAlert:
        return self._transition_alert(alert_id, "INVESTIGATING", field="investigating_at")

    def resolve_alert(self, alert_id: str) -> StrategyAlert:
        return self._transition_alert(alert_id, "RESOLVED", field="resolved_at")

    def _transition_alert(self, alert_id: str, target: str, *, field: str) -> StrategyAlert:
        aid = str(alert_id or "").strip()
        row = self._registry.get_strategy_alert(aid)
        alert = self._alert_from_summary(row)
        try:
            assert_alert_transition(alert.status, target)  # type: ignore[arg-type]
        except InvalidAlertTransitionError as exc:
            raise StrategyMonitoringError(str(exc)) from exc
        ts = _now()
        updates: dict[str, Any] = {"status": target, field: ts}
        alert = alert.model_copy(update=updates)
        return self._writer.write_alert(alert)

    def get_dashboard(self, strategy_code: str) -> DashboardSnapshot:
        code = str(strategy_code or "").strip()
        health = self.get_health(code)
        metrics = self.list_metrics(code, limit=100)
        alerts = self.list_alerts(code)
        fb = load_feedback_scalars(self._feedback, strategy_code=code)
        sections = merge_inject_sections(None)
        recon = sections.get("reconciliation") or {}
        return build_dashboard_snapshot(
            strategy_code=code,
            health=health,
            metrics=metrics,
            alerts=alerts,
            feedback_scalars=fb,
            recon_section=recon,
        )

    def get_performance(self, strategy_code: str) -> dict[str, Any]:
        m = self.list_metrics(strategy_code, category="PERFORMANCE")
        return {x.name: x.value for x in m}

    def get_risk(self, strategy_code: str) -> dict[str, Any]:
        from .bridges.risk_policy import risk_view

        m = self.list_metrics(strategy_code, category="RISK")
        return risk_view({x.name: x.value for x in m})

    def get_execution(self, strategy_code: str) -> dict[str, Any]:
        m = self.list_metrics(strategy_code, category="EXECUTION")
        return {x.name: x.value for x in m}

    def get_drift(self, strategy_code: str) -> dict[str, Any]:
        from .bridges.bridge_from_feedback import drift_view

        return drift_view(load_feedback_scalars(self._feedback, strategy_code=strategy_code))

    def get_reconciliation(self, strategy_code: str) -> dict[str, Any]:
        from .bridges.reconciliation import reconciliation_view

        m = self.list_metrics(strategy_code, category="RECONCILIATION")
        section = {x.name: x.value for x in m}
        for x in m:
            if x.labels.get("severity"):
                section["severity"] = x.labels["severity"]
        return reconciliation_view(section)

    def list_notifications(self, strategy_code: str) -> list[NotificationDispatch]:
        rows = self._registry.list_strategy_notification_dispatches(strategy_code=strategy_code)
        return [
            NotificationDispatch(
                dispatch_id=r.dispatch_id,
                strategy_code=r.strategy_code,
                alert_id=r.alert_id,
                channel=r.channel,  # type: ignore[arg-type]
                severity=r.severity,  # type: ignore[arg-type]
                payload_json=dict(r.payload_json or {}),
                dispatched_at=r.dispatched_at or "",
                session_id=r.session_id or "",
            )
            for r in rows
        ]

    def list_governance_events(self, strategy_code: str) -> list[GovernanceReviewEvent]:
        rows = self._registry.list_strategy_governance_events(strategy_code=strategy_code)
        return [
            GovernanceReviewEvent(
                event_id=r.event_id,
                strategy_code=r.strategy_code,
                event_type=r.event_type,  # type: ignore[arg-type]
                severity=r.severity,  # type: ignore[arg-type]
                category=r.category,  # type: ignore[arg-type]
                alert_id=r.alert_id,
                message=r.message,
                created_at=r.created_at or "",
                session_id=r.session_id or "",
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]


__all__ = ["StrategyMonitoringError", "StrategyMonitoringService"]
