"""Phase 8G：Runtime / Incident / Decision / Event → D1 + R2。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import StrategyGuardrailsArtifactStore
from .protocol import (
    ENGINE_VERSION,
    AutoActionPolicyRecord,
    GovernanceDecision,
    GovernanceEvent,
    GovernanceIncident,
    GuardrailPolicyRecord,
    GuardrailRollbackRecord,
    StrategyRuntimeState,
)


class StrategyGuardrailsWriter:
    """索引与 artifact 写入。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: StrategyGuardrailsArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or StrategyGuardrailsArtifactStore()

    def write_guardrail_policy(self, policy: GuardrailPolicyRecord) -> None:
        from app.services.research_data.contracts import GuardrailPolicySummary

        self._registry.upsert_guardrail_policy(
            GuardrailPolicySummary(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                policy_content_hash=policy.policy_content_hash,
                auto_execute=policy.auto_execute,
                auto_action_policy_id=policy.auto_action_policy_id,
                auto_action_policy_version=policy.auto_action_policy_version,
                action_matrix_json=[e.model_dump(mode="json") for e in policy.action_matrix],
                engine_version=policy.engine_version or ENGINE_VERSION,
                description=policy.description,
            )
        )

    def write_auto_action_policy(self, policy: AutoActionPolicyRecord) -> None:
        from app.services.research_data.contracts import AutoActionPolicySummary

        self._registry.upsert_auto_action_policy(
            AutoActionPolicySummary(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                policy_content_hash=policy.policy_content_hash,
                auto_allowed_json=list(policy.auto_allowed),
                auto_forbidden_json=list(policy.auto_forbidden),
                auto_resume=policy.auto_resume,
                engine_version=policy.engine_version or ENGINE_VERSION,
                description=policy.description,
            )
        )

    def write_runtime(self, state: StrategyRuntimeState) -> StrategyRuntimeState:
        from app.services.research_data.contracts import StrategyRuntimeStateSummary

        uri, cs = self._artifacts.write_runtime(state)
        pinned = state.model_copy(update={"storage_uri": uri})
        self._registry.upsert_strategy_runtime_state(
            StrategyRuntimeStateSummary(
                strategy_code=pinned.strategy_code,
                runtime_status=pinned.runtime_status,
                lifecycle_phase=pinned.lifecycle_phase,
                throttle_tier=pinned.throttle_tier,
                throttle_multiplier=pinned.throttle_multiplier,
                policy_id=pinned.policy_id,
                policy_version=pinned.policy_version,
                policy_content_hash=pinned.policy_content_hash,
                last_incident_id=pinned.last_incident_id,
                recovery_check_passed=pinned.recovery_check_passed,
                last_evaluated_at=pinned.last_evaluated_at,
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_incident(self, incident: GovernanceIncident) -> GovernanceIncident:
        from app.services.research_data.contracts import GovernanceIncidentSummary

        uri, cs = self._artifacts.write_incident(incident)
        pinned = incident.model_copy(update={"storage_uri": uri})
        self._registry.upsert_governance_incident(
            GovernanceIncidentSummary(
                incident_id=pinned.incident_id,
                strategy_code=pinned.strategy_code,
                status=pinned.status,
                severity=pinned.severity,
                category=pinned.category,
                recommended_action=pinned.recommended_action,
                alert_id=pinned.alert_id,
                message=pinned.message,
                requires_decision=pinned.requires_decision,
                opened_at=pinned.opened_at,
                resolved_at=pinned.resolved_at,
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_decision(self, decision: GovernanceDecision) -> GovernanceDecision:
        from app.services.research_data.contracts import GovernanceDecisionSummary

        uri, cs = self._artifacts.write_decision(decision)
        pinned = decision.model_copy(update={"storage_uri": uri})
        self._registry.upsert_governance_decision(
            GovernanceDecisionSummary(
                decision_id=pinned.decision_id,
                strategy_code=pinned.strategy_code,
                incident_id=pinned.incident_id,
                decision_type=pinned.decision_type,
                status=pinned.status,
                operator=pinned.operator,
                reason=pinned.reason,
                to_version=pinned.to_version,
                submitted_at=pinned.submitted_at,
                approved_at=pinned.approved_at,
                executed_at=pinned.executed_at,
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_event(self, event: GovernanceEvent) -> GovernanceEvent:
        from app.services.research_data.contracts import GuardrailGovernanceEventSummary

        self._registry.upsert_guardrail_governance_event(
            GuardrailGovernanceEventSummary(
                event_id=event.event_id,
                strategy_code=event.strategy_code,
                event_type=event.event_type,
                runtime_status=event.runtime_status,
                lifecycle_phase=event.lifecycle_phase,
                severity=event.severity,
                category=event.category,
                incident_id=event.incident_id,
                decision_id=event.decision_id,
                message=event.message,
                created_at=event.created_at,
                session_id=event.session_id,
                engine_version=ENGINE_VERSION,
                metadata=dict(event.metadata),
            )
        )
        uri, _ = self._artifacts.write_event(event)
        return event.model_copy(update={"metadata": {**(event.metadata or {}), "storage_uri": uri}})

    def write_rollback(self, record: GuardrailRollbackRecord) -> GuardrailRollbackRecord:
        from app.services.research_data.contracts import GuardrailRollbackRecordSummary

        uri, cs = self._artifacts.write_rollback(record)
        pinned = record.model_copy(update={"storage_uri": uri})
        self._registry.upsert_guardrail_rollback_record(
            GuardrailRollbackRecordSummary(
                rollback_id=pinned.rollback_id,
                strategy_code=pinned.strategy_code,
                from_version=pinned.from_version,
                to_version=pinned.to_version,
                from_model_version=pinned.from_model_version,
                to_model_version=pinned.to_model_version,
                from_dataset_hash=pinned.from_dataset_hash,
                to_dataset_hash=pinned.to_dataset_hash,
                decision_id=pinned.decision_id,
                reason=pinned.reason,
                operator=pinned.operator,
                session_id=pinned.session_id,
                created_at=pinned.created_at,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned


__all__ = ["StrategyGuardrailsWriter"]
