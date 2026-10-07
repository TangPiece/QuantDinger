"""Phase 7D Golden：Fake MD + Fake broker + LiveTradingRuntime 连续 tick。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
    FakeControlledLiveAdapter,
)
from app.services.controlled_live.artifact_store import ControlledLiveArtifactStore
from app.services.controlled_live.runner import ControlledLiveService
from app.services.controlled_live.runtime import LiveTradingRuntime
from app.services.controlled_live.writers import ControlledLiveWriter
from app.services.ops_service.runner import OpsService
from app.services.reconciliation_service.protocol import ReconciliationRun
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import OrderIntent, ReadinessRunSummary
from app.services.research_data.registry import LocalJsonRegistry
from app.services.shadow_trading.artifact_store import ShadowArtifactStore
from app.services.shadow_trading.runner import ShadowTradingService

DATASET_HASH = "cp_dh_v1"
MODEL_VERSION = "cp_mv_v1"
STRATEGY_VERSION = "cp_sv_v1"
FEATURE_VERSION = "cp_fv_v1"
PROCESSOR_VERSION = "cp_pv_v1"
SNAPSHOT_ID = "cp_snap_v1"
ACCOUNT_ID = "fake-production-acct"
STRATEGY_ID = "strat_production_v1"


class FakeControlledMarketData:
    """CI 用行情健康探针（非真实 HTTP）。"""

    def __init__(self) -> None:
        self._connected = True
        self._stale = False
        self._age_sec = 0.0

    def health(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "stale": self._stale,
            "age_sec": self._age_sec,
        }

    def set_stale(self, *, stale: bool = True, age_sec: float = 999.0) -> None:
        self._stale = stale
        self._age_sec = age_sec

    def set_disconnected(self) -> None:
        self._connected = False


class FakeReconciliationService:
    """可注入 critical_count 的 FAST recon stub。"""

    def __init__(self, *, critical: bool = False) -> None:
        self._critical = critical
        self.run_count = 0

    def run(
        self,
        account_id: str,
        portfolio_id: str,
        *,
        mode: str = "FAST",
        inject: Any = None,
        salt: str = "",
    ) -> ReconciliationRun:
        _ = portfolio_id, inject, salt
        self.run_count += 1
        return ReconciliationRun(
            run_id="recon_fake",
            account_id=account_id,
            mode="FAST",  # type: ignore[arg-type]
            critical_count=1 if self._critical else 0,
            gate_blocked=self._critical,
        )


def _limit_intent(*, trace: str, price: float = 100.0, qty: float = 1.0) -> OrderIntent:
    return OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=qty,
        execution_algorithm="LIMIT",
        limit_price=price,
        trace_id=trace,
        strategy_version=STRATEGY_VERSION,
    )


def make_production_env(
    tmp: Path,
    *,
    broker: FakeControlledLiveAdapter | None = None,
    max_orders: int = 3,
    recon: FakeReconciliationService | None = None,
):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    os.environ["PRODUCTION_READY"] = "true"
    os.environ["CONTROLLED_LIVE_MAX_ORDERS"] = str(max_orders)
    os.environ.pop("CONTROLLED_LIVE_ALLOW_REAL_SUBMIT", None)

    registry.upsert_readiness_run(
        ReadinessRunSummary(
            run_id="cp_golden_rdy",
            production_ready=True,
            metadata={"source": "golden"},
        )
    )

    fake_broker = broker or FakeControlledLiveAdapter()
    fake_md = FakeControlledMarketData()
    fake_recon = recon or FakeReconciliationService()
    ops = OpsService(registry)
    art = ControlledLiveArtifactStore(root=tmp / "cl_raw")
    writer = ControlledLiveWriter(registry, artifact_store=art)

    shadow = ShadowTradingService(
        store,
        registry,
        artifact_store=ShadowArtifactStore(root=tmp / "shadow_raw"),
    )
    shadow.start_session(
        account_id=ACCOUNT_ID,
        dataset_hash=DATASET_HASH,
        model_version=MODEL_VERSION,
        strategy_version=STRATEGY_VERSION,
    )

    controlled = ControlledLiveService(
        store,
        registry,
        shadow=shadow,
        broker_port=fake_broker,
        recon=fake_recon,
        ops=ops,
        writer=writer,
    )
    controlled.start_session(
        account_id=ACCOUNT_ID,
        approved_strategy_id=STRATEGY_ID,
        dataset_hash=DATASET_HASH,
        model_version=MODEL_VERSION,
        strategy_version=STRATEGY_VERSION,
        feature_version=FEATURE_VERSION,
        processor_version=PROCESSOR_VERSION,
        snapshot_id=SNAPSHOT_ID,
    )
    controlled.set_environment(
        "LIVE_CONTROLLED",
        from_env="LIVE_READONLY",
        actor="operator_production",
        approval_token="production-approval-token",
    )
    controlled.approve(
        "operator_production",
        scope="SESSION",
        approval_token="production-approval-token",
    )

    tick_seq = {"n": 0}

    def intent_provider(session, now):  # noqa: ARG001
        tick_seq["n"] += 1
        return [_limit_intent(trace=f"tick{tick_seq['n']}")]

    runtime = LiveTradingRuntime(
        store,
        registry,
        md=fake_md,
        controlled=controlled,
        recon=fake_recon,
        ops=ops,
        shadow=shadow,
        intent_provider=intent_provider,
        writer=writer,
    )
    runtime._session = controlled._session
    return store, registry, controlled, runtime, fake_broker, fake_md, fake_recon, ops
