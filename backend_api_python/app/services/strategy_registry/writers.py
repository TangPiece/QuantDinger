"""Phase 8A：Strategy Registry → D1/LocalJson + manifest。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import StrategyRegistryArtifactStore
from .protocol import ENGINE_VERSION, StrategyRecord, StrategyVersionRecord


class StrategyRegistryWriter:
    """索引与 R2 manifest 写入。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: StrategyRegistryArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or StrategyRegistryArtifactStore()

    def write_strategy(self, record: StrategyRecord) -> None:
        from app.services.research_data.contracts import StrategyRegistrySummary

        rec = StrategyRegistrySummary(
            strategy_code=record.strategy_code,
            display_name=record.display_name,
            owner=record.owner,
            status=record.status,
            active_version=record.active_version,
            created_at=record.created_at,
            engine_version=ENGINE_VERSION,
            metadata=dict(record.metadata or {}),
        )
        self._registry.upsert_strategy_registry(rec)

    def write_version(self, record: StrategyVersionRecord) -> StrategyVersionRecord:
        from app.services.research_data.contracts import StrategyVersionBindingSummary

        uri, cs = self._artifacts.write_version_manifest(record)
        updated = record.model_copy(update={"storage_uri": uri})
        rec = StrategyVersionBindingSummary(
            version_id=updated.version_id,
            strategy_code=updated.strategy_code,
            strategy_version=updated.strategy_version,
            dataset_hash=updated.dataset_hash,
            snapshot_id=updated.snapshot_id,
            model_version=updated.model_version,
            model_artifact_id=updated.model_artifact_id,
            feature_version=updated.feature_version,
            processor_version=updated.processor_version,
            processor_hash=updated.processor_hash,
            strategy_hash=updated.strategy_hash,
            bundle_hash=updated.bundle_hash,
            risk_policy_ref=updated.risk_policy_ref,
            execution_policy_ref=updated.execution_policy_ref,
            content_hash=updated.content_hash,
            source=updated.source,
            registered_at=updated.registered_at,
            storage_uri=uri,
            engine_version=ENGINE_VERSION,
            metadata={**(updated.metadata or {}), "checksum": cs},
        )
        self._registry.upsert_strategy_version_binding(rec)
        return updated
