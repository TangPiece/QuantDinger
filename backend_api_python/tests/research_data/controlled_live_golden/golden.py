"""Phase 7C Golden：Controlled Live + Shadow（Fake broker 默认）。"""

from __future__ import annotations

import os
from pathlib import Path

from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
    FakeControlledLiveAdapter,
)
from app.services.controlled_live.artifact_store import ControlledLiveArtifactStore
from app.services.controlled_live.runner import ControlledLiveService
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import ReadinessRunSummary
from app.services.research_data.registry import LocalJsonRegistry
from app.services.shadow_trading.artifact_store import ShadowArtifactStore
from app.services.shadow_trading.runner import ShadowTradingService

DATASET_HASH = "cl_dh_v1"
MODEL_VERSION = "cl_mv_v1"
STRATEGY_VERSION = "cl_sv_v1"
ACCOUNT_ID = "fake-controlled-acct"
STRATEGY_ID = "strat_controlled_v1"


def make_env(tmp: Path, *, broker: FakeControlledLiveAdapter | None = None):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    os.environ["PRODUCTION_READY"] = "true"
    os.environ["CONTROLLED_LIVE_MAX_ORDERS"] = "1"
    os.environ.pop("CONTROLLED_LIVE_ALLOW_REAL_SUBMIT", None)
    registry.upsert_readiness_run(
        ReadinessRunSummary(
            run_id="cl_golden_rdy",
            production_ready=True,
            metadata={"source": "golden"},
        )
    )

    fake_broker = broker or FakeControlledLiveAdapter()
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
        writer=None,
    )
    controlled._writer._artifacts = ControlledLiveArtifactStore(root=tmp / "cl_raw")
    controlled.start_session(
        account_id=ACCOUNT_ID,
        approved_strategy_id=STRATEGY_ID,
        dataset_hash=DATASET_HASH,
        model_version=MODEL_VERSION,
        strategy_version=STRATEGY_VERSION,
    )
    controlled.set_environment(
        "LIVE_CONTROLLED",
        from_env="LIVE_READONLY",
        actor="operator_golden",
        approval_token="golden-approval-token",
    )
    controlled.approve("operator_golden", approval_token="golden-approval-token")
    return store, registry, shadow, controlled, fake_broker
