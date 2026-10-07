"""Phase 8H：Dataset / Snapshot / FailureCase → D1 + R2。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ProductionResearchFeedbackArtifactStore
from .protocol import (
    ENGINE_VERSION,
    CounterfactualRecord,
    FeedbackExperimentLink,
    ProductionFeedbackDataset,
    ProductionRealitySnapshot,
    ResearchFailureCase,
    ResearchHypothesis,
)


class SnapshotImmutableError(RuntimeError):
    """已发布 Snapshot 禁止覆盖。"""


class ProductionResearchFeedbackWriter:
    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ProductionResearchFeedbackArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ProductionResearchFeedbackArtifactStore()

    def write_dataset(self, record: ProductionFeedbackDataset) -> ProductionFeedbackDataset:
        from app.services.research_data.contracts import ProductionFeedbackDatasetSummary

        uri, cs = self._artifacts.write_dataset(record)
        pinned = record.model_copy(update={"storage_uri": uri})
        self._registry.upsert_production_feedback_dataset(
            ProductionFeedbackDatasetSummary(
                dataset_id=pinned.dataset_id,
                strategy_code=pinned.strategy_code,
                feedback_type=pinned.feedback_type,
                dataset_hash=pinned.dataset_hash,
                schema_version=pinned.schema_version,
                filter_spec_json=dict(pinned.filter_spec),
                window_start=pinned.window_start,
                window_end=pinned.window_end,
                processor_id=pinned.processor_id,
                processor_version=pinned.processor_version,
                quality_gate_verdict=pinned.quality_gate_verdict,
                lineage_json=pinned.lineage.model_dump(mode="json"),
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_snapshot(
        self,
        record: ProductionRealitySnapshot,
        *,
        allow_supersede: bool = False,
    ) -> ProductionRealitySnapshot:
        from app.services.research_data.contracts import ProductionRealitySnapshotSummary

        existing = None
        try:
            existing = self._registry.get_production_reality_snapshot(record.snapshot_id)
        except KeyError:
            existing = None
        if existing is not None and not allow_supersede:
            if (
                existing.snapshot_version == record.snapshot_version
                and existing.content_hash != record.content_hash
            ):
                raise SnapshotImmutableError(
                    f"snapshot immutable: {record.snapshot_id} v{record.snapshot_version}"
                )
            if (
                existing.snapshot_version == record.snapshot_version
                and existing.content_hash == record.content_hash
            ):
                return record.model_copy(update={"storage_uri": existing.storage_uri or record.storage_uri})

        uri, cs = self._artifacts.write_snapshot(record)
        pinned = record.model_copy(update={"storage_uri": uri})
        self._registry.upsert_production_reality_snapshot(
            ProductionRealitySnapshotSummary(
                snapshot_id=pinned.snapshot_id,
                snapshot_version=pinned.snapshot_version,
                supersedes_snapshot_id=pinned.supersedes_snapshot_id,
                strategy_code=pinned.strategy_code,
                reality_kind=pinned.reality_kind,
                as_of_time=pinned.as_of_time,
                pnl_total=pinned.pnl_summary.pnl_total,
                metrics_json=dict(pinned.metrics),
                dataset_id=pinned.dataset_id,
                content_hash=pinned.content_hash,
                lineage_json=pinned.lineage.model_dump(mode="json"),
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_failure_case(self, record: ResearchFailureCase) -> ResearchFailureCase:
        from app.services.research_data.contracts import ResearchFailureCaseSummary

        uri, cs = self._artifacts.write_failure_case(record)
        pinned = record.model_copy(update={"storage_uri": uri})
        self._registry.upsert_research_failure_case(
            ResearchFailureCaseSummary(
                case_id=pinned.case_id,
                strategy_code=pinned.strategy_code,
                incident_id=pinned.incident_id,
                governance_decision_id=pinned.governance_decision_id,
                dataset_hash=pinned.dataset_hash,
                feedback_dataset_id=pinned.feedback_dataset_id,
                category=pinned.category,
                severity=pinned.severity,
                summary=pinned.summary,
                lineage_json=pinned.lineage.model_dump(mode="json"),
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_hypothesis(self, record: ResearchHypothesis) -> ResearchHypothesis:
        from app.services.research_data.contracts import ResearchHypothesisSummary

        uri, cs = self._artifacts.write_hypothesis(record)
        pinned = record.model_copy(update={"storage_uri": uri})
        self._registry.upsert_research_hypothesis(
            ResearchHypothesisSummary(
                hypothesis_id=pinned.hypothesis_id,
                strategy_code=pinned.strategy_code,
                status=pinned.status,
                failure_case_ids_json=list(pinned.failure_case_ids),
                feedback_dataset_id=pinned.feedback_dataset_id,
                title=pinned.title,
                description=pinned.description,
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_experiment_link(self, record: FeedbackExperimentLink) -> FeedbackExperimentLink:
        from app.services.research_data.contracts import FeedbackExperimentLinkSummary

        uri, cs = self._artifacts.write_experiment_link(record)
        pinned = record.model_copy(update={"storage_uri": uri})
        self._registry.upsert_feedback_experiment_link(
            FeedbackExperimentLinkSummary(
                link_id=pinned.link_id,
                experiment_id=pinned.experiment_id,
                strategy_code=pinned.strategy_code,
                parent_feedback_dataset_id=pinned.parent_feedback_dataset_id,
                parent_failure_case_ids_json=list(pinned.parent_failure_case_ids),
                parent_incident_ids_json=list(pinned.parent_incident_ids),
                hypothesis_id=pinned.hypothesis_id,
                session_id=pinned.session_id,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs, **(pinned.metadata or {})},
            )
        )
        return pinned

    def write_counterfactual(self, record: CounterfactualRecord) -> CounterfactualRecord:
        uri, cs = self._artifacts.write_counterfactual(record)
        pinned = record.model_copy(update={"storage_uri": uri, "metadata": {**(record.metadata or {}), "checksum": cs}})
        return pinned


__all__ = ["ProductionResearchFeedbackWriter", "SnapshotImmutableError"]
