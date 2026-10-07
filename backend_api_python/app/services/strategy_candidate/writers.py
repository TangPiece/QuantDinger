"""Phase 8B：Strategy Candidate → D1/LocalJson + manifest。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import StrategyCandidateArtifactStore
from .protocol import ENGINE_VERSION, PromotionRecord, StrategyCandidateRecord


class StrategyCandidateWriter:
    """索引与 R2 manifest 写入。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: StrategyCandidateArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or StrategyCandidateArtifactStore()

    def write_candidate(self, record: StrategyCandidateRecord) -> StrategyCandidateRecord:
        from app.services.research_data.contracts import StrategyCandidateSummary

        uri, cs = self._artifacts.write_manifest(record)
        updated = record.model_copy(update={"storage_uri": uri})
        rec = StrategyCandidateSummary(
            candidate_id=updated.candidate_id,
            strategy_code=updated.strategy_code,
            candidate_version=updated.candidate_version,
            experiment_id=updated.experiment_id,
            backtest_hash=updated.backtest_hash,
            model_version=updated.model_version,
            model_artifact_id=updated.model_artifact_id,
            dataset_hash=updated.dataset_hash,
            snapshot_id=updated.snapshot_id,
            feature_version=updated.feature_version,
            processor_version=updated.processor_version,
            processor_hash=updated.processor_hash,
            strategy_hash=updated.strategy_hash,
            strategy_definition_json=dict(updated.strategy_definition_json or {}),
            risk_policy_ref=updated.risk_policy_ref,
            execution_policy_ref=updated.execution_policy_ref,
            evaluation_hash=updated.evaluation_hash,
            cv_hash=updated.cv_hash,
            content_hash=updated.content_hash,
            source=updated.source,
            status=updated.status,
            lineage_frozen_at=updated.lineage_frozen_at,
            created_at=updated.created_at,
            storage_uri=uri,
            engine_version=ENGINE_VERSION,
            metadata={**(updated.metadata or {}), "checksum": cs, "lineage_frozen": updated.lineage_frozen},
        )
        self._registry.upsert_strategy_candidate(rec)
        return updated

    def write_promotion(self, record: PromotionRecord) -> None:
        from app.services.research_data.contracts import StrategyCandidatePromotionSummary

        rec = StrategyCandidatePromotionSummary(
            promotion_id=record.promotion_id,
            candidate_id=record.candidate_id,
            source_type=record.source_type,
            source_id=record.source_id,
            target_strategy_code=record.target_strategy_code,
            target_strategy_version=record.target_strategy_version,
            version_id=record.version_id,
            from_state=record.from_state,
            to_state=record.to_state,
            dataset_hash=record.dataset_hash,
            model_version=record.model_version,
            operator=record.operator,
            reason=record.reason,
            status=record.status,
            created_at=record.created_at,
            engine_version=ENGINE_VERSION,
            metadata={},
        )
        self._registry.upsert_strategy_candidate_promotion(rec)


__all__ = ["StrategyCandidateWriter"]
