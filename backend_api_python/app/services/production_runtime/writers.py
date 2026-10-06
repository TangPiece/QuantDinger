"""Runtime / Event / Run → Registry + Artifact。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import (
    ProductionRuntimeEventRecord,
    ProductionRuntimeRunSummary,
    ProductionRuntimeSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ProductionRuntimeArtifactStore
from .protocol import ENGINE_VERSION, RuntimeInstance, RuntimeTickResult


class ProductionRuntimeWriter:
    """写 Runtime 实例 / 事件 / run。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ProductionRuntimeArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ProductionRuntimeArtifactStore()

    def write_instance(self, instance: RuntimeInstance) -> ProductionRuntimeSummary:
        art = self._artifacts.write_manifest(instance)
        summary = ProductionRuntimeSummary(
            runtime_id=instance.runtime_id,
            bundle_hash=instance.bundle_hash,
            strategy_code=instance.strategy_code,
            market=instance.market,
            environment=instance.environment,
            status=instance.status,
            session_phase=instance.session_phase,
            trading_date=instance.trading_date,
            started_at=instance.started_at,
            last_heartbeat=instance.last_heartbeat,
            engine_version=instance.engine_version or ENGINE_VERSION,
            storage_uri=art.storage_uri,
            metadata=dict(instance.metadata or {}),
        )
        self._registry.upsert_production_runtime(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary

    def update_instance(self, instance: RuntimeInstance) -> ProductionRuntimeSummary:
        summary = ProductionRuntimeSummary(
            runtime_id=instance.runtime_id,
            bundle_hash=instance.bundle_hash,
            strategy_code=instance.strategy_code,
            market=instance.market,
            environment=instance.environment,
            status=instance.status,
            session_phase=instance.session_phase,
            trading_date=instance.trading_date,
            started_at=instance.started_at,
            last_heartbeat=instance.last_heartbeat,
            engine_version=instance.engine_version or ENGINE_VERSION,
            storage_uri=instance.storage_uri,
            metadata=dict(instance.metadata or {}),
        )
        self._registry.upsert_production_runtime(summary)
        return summary

    def write_event(self, event: ProductionRuntimeEventRecord) -> None:
        self._registry.append_runtime_event(event)
        try:
            self._artifacts.append_event_file(
                event.runtime_id, event.model_dump(mode="json")
            )
        except Exception:
            pass

    def write_run(
        self,
        result: RuntimeTickResult,
        *,
        bridge_payload: dict[str, Any] | None = None,
    ) -> ProductionRuntimeRunSummary:
        uri = self._artifacts.write_run(result, bridge_payload=bridge_payload)
        rec = ProductionRuntimeRunSummary(
            run_id=result.run_id,
            runtime_id=result.runtime_id,
            bundle_hash=str((result.metadata or {}).get("bundle_hash") or ""),
            idempotency_key=result.idempotency_key,
            trading_date=result.trading_date,
            session_phase=result.session_phase,
            status=result.status,
            n_signals=len(result.signals),
            n_intents=len(result.order_intents),
            bridge_run_id=result.bridge_run_id,
            storage_uri=uri,
            metadata=dict(result.metadata or {}),
        )
        self._registry.upsert_runtime_run(rec)
        return rec
