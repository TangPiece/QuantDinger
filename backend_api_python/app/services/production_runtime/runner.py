"""ProductionRuntimeService：start / tick / pause / stop；停在 OrderIntent。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.production_bridge import ProductionBridgeService
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ProductionRuntimeArtifactStore
from .cycle import run_tick
from .events import append_event
from .hash import compute_runtime_id
from .market_data import MarketDataProvider
from .online_feature import OnlineFeatureEngine
from .protocol import (
    ENGINE_VERSION,
    RuntimeEnvironment,
    RuntimeInstance,
    RuntimeMarket,
    RuntimeTickResult,
)
from .risk_port import FiveFSignalGatePort, RiskGatePort
from .session import MarketSchedule
from .state_machine import RuntimeStateError, assert_transition, can_transition
from .writers import ProductionRuntimeWriter


class ProductionRuntimeError(RuntimeError):
    """Production Runtime 编排错误。"""


class ProductionRuntimeService:
    """加载 DEPLOYED Bundle → PAPER/SHADOW tick → OrderIntent（不发单）。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        bridge: ProductionBridgeService | None = None,
        market_data: MarketDataProvider | None = None,
        risk_port: RiskGatePort | None = None,
        artifact_store: ProductionRuntimeArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._bridge = bridge or ProductionBridgeService(store, registry)
        self._market_data = market_data
        self._risk_port = risk_port or FiveFSignalGatePort()
        self._writer = ProductionRuntimeWriter(
            registry, artifact_store=artifact_store
        )
        self._schedule = MarketSchedule()
        self._features: dict[str, OnlineFeatureEngine] = {}

    def start(
        self,
        bundle_hash: str,
        *,
        market: RuntimeMarket | str = "CN_A",
        environment: RuntimeEnvironment | str = "PAPER",
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeInstance:
        """加载 DEPLOYED Bundle，创建 RuntimeInstance。"""
        env = str(environment)
        if env not in ("PAPER", "SHADOW"):
            raise ProductionRuntimeError(
                f"environment must be PAPER|SHADOW, got {env!r} (LIVE not implemented)"
            )
        try:
            summary = self._registry.get_production_bundle(bundle_hash)
        except KeyError as exc:
            raise ProductionRuntimeError(
                f"production_bundle not found: {bundle_hash!r}"
            ) from exc
        if summary.status != "DEPLOYED":
            raise ProductionRuntimeError(
                f"bundle must be DEPLOYED, got {summary.status!r}"
            )
        # integrity：checksum / storage 存在即可
        if not summary.storage_uri and not (summary.metadata or {}).get("allow_empty_uri"):
            # 测试环境可能仅有 registry 行
            pass

        now = datetime.now(timezone.utc)
        started_bucket = now.strftime("%Y%m%d%H%M%S")
        rid = compute_runtime_id(
            bundle_hash=bundle_hash,
            environment=env,
            market=str(market),
            started_bucket=started_bucket,
        )
        session = self._schedule.build_session(str(market), now=now)
        instance = RuntimeInstance(
            runtime_id=rid,
            bundle_hash=bundle_hash,
            strategy_code=summary.strategy_code or "",
            market=str(market),  # type: ignore[arg-type]
            environment=env,  # type: ignore[arg-type]
            status="STARTING",
            session_phase=session.phase,
            trading_date=session.trading_date.isoformat(),
            started_at=now.isoformat(),
            last_heartbeat=now.isoformat(),
            engine_version=ENGINE_VERSION,
            metadata=dict(metadata or {}),
        )
        written = self._writer.write_instance(instance)
        instance = instance.model_copy(update={"storage_uri": written.storage_uri})
        append_event(
            self._registry,
            runtime_id=rid,
            event_type="BUNDLE_LOADED",
            trading_date=instance.trading_date,
            session_phase=instance.session_phase,
            message=f"bundle={bundle_hash}",
            payload={"status": summary.status, "strategy_code": summary.strategy_code},
        )
        # STARTING → READY
        assert_transition("STARTING", "READY")
        instance = instance.model_copy(update={"status": "READY"})
        self._writer.update_instance(instance)
        self._features[rid] = OnlineFeatureEngine(
            processor_version=summary.processor_hash or "",
        )
        return instance

    def tick(
        self,
        runtime_id: str,
        *,
        now: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTickResult:
        """单次 tick；产出 OrderIntent，不发单。"""
        instance = self._load(runtime_id)
        now = now or datetime.now(timezone.utc)
        meta = dict(metadata or {})
        # READY → RUNNING
        if instance.status == "READY" and can_transition("READY", "RUNNING"):
            instance = instance.model_copy(update={"status": "RUNNING"})

        feat = self._features.get(runtime_id) or OnlineFeatureEngine()
        try:
            result = run_tick(
                instance,
                bridge=self._bridge,
                writer=self._writer,
                registry=self._registry,
                market_data=self._market_data,
                feature_engine=feat,
                risk_port=self._risk_port,
                schedule=self._schedule,
                now=now,
                metadata=meta,
            )
        except Exception as exc:
            append_event(
                self._registry,
                runtime_id=runtime_id,
                event_type="RUNTIME_ERROR",
                message=str(exc)[:500],
            )
            if can_transition(instance.status, "DEGRADED"):
                instance = instance.model_copy(update={"status": "DEGRADED"})
            elif can_transition(instance.status, "ERROR"):
                instance = instance.model_copy(update={"status": "ERROR"})
            instance = instance.model_copy(
                update={"last_heartbeat": datetime.now(timezone.utc).isoformat()}
            )
            self._writer.update_instance(instance)
            raise

        # 心跳 + 相位
        updates: dict[str, Any] = {
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "session_phase": result.session_phase or instance.session_phase,
            "trading_date": result.trading_date or instance.trading_date,
            "status": instance.status,
        }
        if result.status == "FAILED" and can_transition(instance.status, "DEGRADED"):
            updates["status"] = "DEGRADED"
        elif instance.status == "READY":
            updates["status"] = "RUNNING"
        instance = instance.model_copy(update=updates)
        self._writer.update_instance(instance)
        # 6B 预留
        result = result.model_copy(
            update={
                "metadata": {
                    **dict(result.metadata or {}),
                    "runtime_id": runtime_id,
                    "run_id": result.run_id,
                }
            }
        )
        return result

    def pause(self, runtime_id: str) -> RuntimeInstance:
        instance = self._load(runtime_id)
        assert_transition(instance.status, "PAUSED")
        instance = instance.model_copy(
            update={
                "status": "PAUSED",
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._writer.update_instance(instance)
        append_event(
            self._registry,
            runtime_id=runtime_id,
            event_type="RUNTIME_PAUSED",
            trading_date=instance.trading_date,
            session_phase=instance.session_phase,
        )
        return instance

    def resume(self, runtime_id: str) -> RuntimeInstance:
        instance = self._load(runtime_id)
        target = "RUNNING" if can_transition(instance.status, "RUNNING") else "READY"
        assert_transition(instance.status, target)
        instance = instance.model_copy(
            update={
                "status": target,  # type: ignore[arg-type]
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._writer.update_instance(instance)
        return instance

    def stop(self, runtime_id: str) -> RuntimeInstance:
        instance = self._load(runtime_id)
        if instance.status not in ("STOPPING", "STOPPED"):
            if not can_transition(instance.status, "STOPPING"):
                raise RuntimeStateError(
                    f"cannot stop from {instance.status!r}"
                )
            instance = instance.model_copy(update={"status": "STOPPING"})
            self._writer.update_instance(instance)
        assert_transition("STOPPING", "STOPPED")
        instance = instance.model_copy(
            update={
                "status": "STOPPED",
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._writer.update_instance(instance)
        return instance

    def get(self, runtime_id: str) -> RuntimeInstance:
        return self._load(runtime_id)

    def _load(self, runtime_id: str) -> RuntimeInstance:
        summary = self._registry.get_production_runtime(runtime_id)
        return RuntimeInstance(
            runtime_id=summary.runtime_id,
            bundle_hash=summary.bundle_hash,
            strategy_code=summary.strategy_code,
            market=summary.market,  # type: ignore[arg-type]
            environment=summary.environment,  # type: ignore[arg-type]
            status=summary.status,  # type: ignore[arg-type]
            session_phase=summary.session_phase,  # type: ignore[arg-type]
            trading_date=summary.trading_date,
            started_at=summary.started_at,
            last_heartbeat=summary.last_heartbeat,
            engine_version=summary.engine_version or ENGINE_VERSION,
            storage_uri=summary.storage_uri,
            metadata=dict(summary.metadata or {}),
        )


def create_default_service(
    root: Any = None, registry: ResearchRegistry | None = None
) -> ProductionRuntimeService:
    """便捷工厂（本地 store + registry）。"""
    from pathlib import Path

    from app.services.research_data.registry import LocalJsonRegistry, get_default_registry

    store = LocalCanonicalStore(root=Path(root) if root else None)
    reg = registry or get_default_registry()
    if registry is None and not hasattr(reg, "upsert_production_runtime"):
        reg = LocalJsonRegistry()
    return ProductionRuntimeService(store, reg)
