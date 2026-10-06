"""Production Bundle / Deployment → Registry。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import (
    ProductionBundleSummary,
    ProductionDeploymentRunSummary,
    ProductionDeploymentSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ProductionBundleArtifactStore
from .protocol import (
    ENGINE_VERSION,
    BundleManifest,
    FeatureParityReport,
    InferenceResponse,
    ProductionBundleSpec,
)


class ProductionBundleWriter:
    """写 Bundle artifact + Registry。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ProductionBundleArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ProductionBundleArtifactStore()

    def write_bundle(
        self,
        spec: ProductionBundleSpec,
        *,
        bundle_hash: str,
        status: str = "DRAFT",
        parity: FeatureParityReport | None = None,
        force: bool = False,
    ) -> ProductionBundleSummary:
        if not force:
            try:
                existing = self._registry.get_production_bundle(bundle_hash)
                return existing
            except (KeyError, AttributeError):
                pass

        summary = ProductionBundleSummary(
            bundle_hash=bundle_hash,
            strategy_hash=spec.strategy_hash,
            strategy_code=spec.strategy_code,
            cv_hash=spec.cv_hash,
            backtest_hash=spec.backtest_hash,
            qlib_run_hash=spec.qlib_run_hash,
            dataset_hash=spec.dataset_hash,
            materialization_id=spec.materialization_id,
            model_artifact_id=spec.model_artifact_id,
            model_version=spec.model_version,
            processor_hash=spec.processor_hash,
            processor_artifact_uri=spec.processor_artifact_uri,
            pipeline_digest=spec.pipeline_digest,
            universe_code=spec.universe_code,
            snapshot_id=spec.snapshot_id,
            execution_policy=spec.execution_policy,
            realism=spec.realism,
            market_rule=spec.market_rule if spec.realism == "NET" else "",
            status=status,
            parent_bundle_hash=spec.parent_bundle_hash,
            dependency_lock_json=spec.dependency_lock.model_dump(mode="json"),
            feature_hashes=list(spec.feature_hashes or []),
            engine_version=spec.bundle_engine_version or ENGINE_VERSION,
            metadata=dict(spec.metadata or {}),
        )
        man = BundleManifest(
            bundle_hash=bundle_hash,
            strategy_hash=spec.strategy_hash,
            engine_version=summary.engine_version,
        )
        processor = None
        if spec.processor_hash or spec.pipeline_digest:
            processor = {
                "processor_hash": spec.processor_hash,
                "pipeline_digest": spec.pipeline_digest,
                "artifact_uri": spec.processor_artifact_uri,
            }
        model_pointer = None
        if spec.model_artifact_id:
            model_pointer = {
                "model_artifact_id": spec.model_artifact_id,
                "model_version": spec.model_version,
            }
        art = self._artifacts.write_bundle(
            man,
            summary=summary,
            dependency_lock=summary.dependency_lock_json,
            processor=processor,
            model_pointer=model_pointer,
            parity=parity,
        )
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_production_bundle(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary

    def update_status(
        self, bundle_hash: str, status: str, *, metadata: dict[str, Any] | None = None
    ) -> ProductionBundleSummary:
        summary = self._registry.get_production_bundle(bundle_hash)
        updates: dict[str, Any] = {"status": status}
        if metadata:
            meta = dict(summary.metadata or {})
            meta.update(metadata)
            updates["metadata"] = meta
        summary = summary.model_copy(update=updates)
        self._registry.upsert_production_bundle(summary)
        return summary

    def write_deployment(
        self, record: ProductionDeploymentSummary
    ) -> ProductionDeploymentSummary:
        self._registry.upsert_production_deployment(record)
        return record

    def write_run(
        self, response: InferenceResponse, *, deployment_id: str = ""
    ) -> ProductionDeploymentRunSummary:
        uri = self._artifacts.write_run(response)
        rec = ProductionDeploymentRunSummary(
            run_id=response.run_id,
            bundle_hash=response.bundle_hash,
            deployment_id=deployment_id,
            trading_date=response.trading_date,
            status=response.status,
            n_signals=len(response.signals),
            n_intents=len(response.order_intents),
            gate_json={
                "gates": [g.model_dump(mode="json") for g in response.gate_results]
            },
            storage_uri=uri,
            metadata=dict(response.metadata or {}),
        )
        self._registry.upsert_deployment_run(rec)
        return rec
