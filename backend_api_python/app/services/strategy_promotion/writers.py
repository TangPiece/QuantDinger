"""Phase 8D：Promotion Request/Run/Rollback/Policy → D1 + R2。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import PromotionArtifactStore
from .protocol import (
    ENGINE_VERSION,
    PromotionPolicyRecord,
    PromotionRequest,
    PromotionRunRecord,
    RollbackRecord,
)


class PromotionWriter:
    """索引与 manifest 写入。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: PromotionArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or PromotionArtifactStore()

    def write_policy(self, policy: PromotionPolicyRecord) -> None:
        from app.services.research_data.contracts import StrategyPromotionPolicySummary

        self._registry.upsert_strategy_promotion_policy(
            StrategyPromotionPolicySummary(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                transition_key=policy.transition_key,
                policy_content_hash=policy.policy_content_hash,
                rules_json=policy.rules.model_dump(mode="json"),
                engine_version=policy.engine_version or ENGINE_VERSION,
                description=policy.description,
            )
        )

    def write_request(self, req: PromotionRequest) -> PromotionRequest:
        from app.services.research_data.contracts import StrategyPromotionRequestSummary

        self._registry.upsert_strategy_promotion_request(
            StrategyPromotionRequestSummary(
                request_id=req.request_id,
                pipeline_run_id=req.pipeline_run_id,
                idempotency_key=req.idempotency_key,
                strategy_code=req.strategy_code,
                candidate_id=req.candidate_id,
                validation_id=req.validation_id,
                strategy_version=req.strategy_version,
                version_id=req.version_id,
                content_hash=req.content_hash,
                from_environment=req.from_environment,
                to_environment=req.to_environment,
                policy_id=req.policy_id,
                policy_version=req.policy_version,
                policy_content_hash=req.policy_content_hash,
                status=req.status,
                operator=req.operator,
                approvals_json=[a.model_dump(mode="json") for a in req.approvals],
                created_at=req.created_at,
                updated_at=req.updated_at,
                engine_version=ENGINE_VERSION,
            )
        )
        return req

    def write_run(self, run: PromotionRunRecord) -> PromotionRunRecord:
        from app.services.research_data.contracts import StrategyPromotionRunSummary

        uri, cs = self._artifacts.write_manifest(run)
        completed = run.model_copy(update={"storage_uri": uri})
        self._registry.upsert_strategy_promotion_run(
            StrategyPromotionRunSummary(
                pipeline_run_id=completed.pipeline_run_id,
                request_id=completed.request_id,
                strategy_code=completed.strategy_code,
                from_environment=completed.from_environment,
                to_environment=completed.to_environment,
                policy_id=completed.policy_id,
                policy_version=completed.policy_version,
                policy_content_hash=completed.policy_content_hash,
                status=completed.status,
                stages_json=[s.model_dump(mode="json") for s in completed.stages],
                session_id=completed.session_id,
                governance_state=completed.governance_state,
                started_at=completed.started_at,
                completed_at=completed.completed_at,
                operator=completed.operator,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs},
            )
        )
        return completed

    def write_rollback(self, rec: RollbackRecord) -> RollbackRecord:
        from app.services.research_data.contracts import StrategyPromotionRollbackSummary

        self._registry.upsert_strategy_promotion_rollback(
            StrategyPromotionRollbackSummary(
                rollback_id=rec.rollback_id,
                strategy_code=rec.strategy_code,
                from_version=rec.from_version,
                to_version=rec.to_version,
                reason=rec.reason,
                operator=rec.operator,
                session_id=rec.session_id,
                created_at=rec.created_at,
                engine_version=ENGINE_VERSION,
            )
        )
        return rec


__all__ = ["PromotionWriter"]
