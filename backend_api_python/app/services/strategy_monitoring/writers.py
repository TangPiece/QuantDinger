"""Phase 8F：Metrics / Health / Alert / Policy → D1 + R2。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import StrategyMonitoringArtifactStore
from .protocol import (
    ENGINE_VERSION,
    GovernanceReviewEvent,
    MonitoringMetric,
    MonitorPolicyRecord,
    NotificationDispatch,
    StrategyAlert,
    StrategyHealth,
)


class StrategyMonitoringWriter:
    """索引与 artifact 写入。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: StrategyMonitoringArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or StrategyMonitoringArtifactStore()

    def write_policy(self, policy: MonitorPolicyRecord) -> None:
        from app.services.research_data.contracts import StrategyMonitorPolicySummary

        self._registry.upsert_strategy_monitor_policy(
            StrategyMonitorPolicySummary(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                policy_content_hash=policy.policy_content_hash,
                rules_json=[r.model_dump(mode="json") for r in policy.rules],
                market_data_json=policy.market_data.model_dump(mode="json"),
                engine_version=policy.engine_version or ENGINE_VERSION,
                description=policy.description,
            )
        )

    def write_metric(self, metric: MonitoringMetric) -> MonitoringMetric:
        from app.services.research_data.contracts import StrategyMonitorMetricSummary

        uri, cs = self._artifacts.write_metric(metric)
        self._registry.upsert_strategy_monitor_metric(
            StrategyMonitorMetricSummary(
                metric_id=metric.metric_id,
                strategy_code=metric.strategy_code,
                category=metric.category,
                name=metric.name,
                value=metric.value,
                unit=metric.unit,
                health=metric.health,
                window=metric.window,
                collected_at=metric.collected_at,
                session_id=metric.session_id,
                labels_json=dict(metric.labels),
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs},
            )
        )
        return metric

    def write_health(self, health: StrategyHealth) -> StrategyHealth:
        from app.services.research_data.contracts import StrategyHealthSnapshotSummary

        uri, cs = self._artifacts.write_health(health)
        pinned = health.model_copy(update={"storage_uri": uri})
        self._registry.upsert_strategy_health_snapshot(
            StrategyHealthSnapshotSummary(
                snapshot_id=pinned.snapshot_id,
                strategy_code=pinned.strategy_code,
                overall=pinned.overall,
                dimensions_json=[d.model_dump(mode="json") for d in pinned.dimensions],
                policy_id=pinned.policy_id,
                policy_version=pinned.policy_version,
                policy_content_hash=pinned.policy_content_hash,
                evaluated_at=pinned.evaluated_at,
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs},
            )
        )
        return pinned

    def write_alert(self, alert: StrategyAlert) -> StrategyAlert:
        from app.services.research_data.contracts import StrategyAlertSummary

        uri, cs = self._artifacts.write_alert(alert)
        self._registry.upsert_strategy_alert(
            StrategyAlertSummary(
                alert_id=alert.alert_id,
                strategy_code=alert.strategy_code,
                rule_id=alert.rule_id,
                fingerprint=alert.fingerprint,
                category=alert.category,
                severity=alert.severity,
                status=alert.status,
                title=alert.title,
                message=alert.message,
                occurrence_count=alert.occurrence_count,
                consecutive_critical_count=alert.consecutive_critical_count,
                first_seen_at=alert.first_seen_at,
                last_seen_at=alert.last_seen_at,
                cooldown_until=alert.cooldown_until,
                suppressed_until=alert.suppressed_until,
                acknowledged_at=alert.acknowledged_at,
                investigating_at=alert.investigating_at,
                resolved_at=alert.resolved_at,
                session_id=alert.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(alert.metadata or {})},
            )
        )
        return alert

    def write_notification(self, dispatch: NotificationDispatch) -> None:
        from app.services.research_data.contracts import StrategyNotificationDispatchSummary

        self._registry.upsert_strategy_notification_dispatch(
            StrategyNotificationDispatchSummary(
                dispatch_id=dispatch.dispatch_id,
                strategy_code=dispatch.strategy_code,
                alert_id=dispatch.alert_id,
                channel=dispatch.channel,
                severity=dispatch.severity,
                payload_json=dict(dispatch.payload_json),
                dispatched_at=dispatch.dispatched_at,
                session_id=dispatch.session_id,
                engine_version=ENGINE_VERSION,
            )
        )

    def write_governance_event(self, event: GovernanceReviewEvent) -> None:
        from app.services.research_data.contracts import StrategyGovernanceEventSummary

        self._registry.upsert_strategy_governance_event(
            StrategyGovernanceEventSummary(
                event_id=event.event_id,
                strategy_code=event.strategy_code,
                event_type=event.event_type,
                severity=event.severity,
                category=event.category,
                alert_id=event.alert_id,
                message=event.message,
                created_at=event.created_at,
                session_id=event.session_id,
                engine_version=ENGINE_VERSION,
                metadata=dict(event.metadata),
            )
        )


__all__ = ["StrategyMonitoringWriter"]
