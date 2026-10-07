"""Phase 7B Golden：Shadow + Live MD（Fake transport）。"""

from __future__ import annotations

import os
from pathlib import Path

from app.services.live_market_data.artifact_store import LiveMdArtifactStore
from app.services.live_market_data.runner import LiveMarketDataService
from app.services.live_market_data.transport import FakeLiveMdTransport
from app.services.live_readonly.adapter import fake_adapter
from app.services.live_readonly.artifact_store import LiveReadonlyArtifactStore
from app.services.live_readonly.runner import LiveReadonlyService
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import ReadinessRunSummary
from app.services.research_data.registry import LocalJsonRegistry
from app.services.shadow_trading.artifact_store import ShadowArtifactStore
from app.services.shadow_trading.runner import ShadowTradingService

DATASET_HASH = "sh_dh_v1"
MODEL_VERSION = "sh_mv_v1"
STRATEGY_VERSION = "sh_sv_v1"
ACCOUNT_ID = "fake-live-acct"


def make_env(tmp: Path):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    os.environ["PRODUCTION_READY"] = "true"
    registry.upsert_readiness_run(
        ReadinessRunSummary(
            run_id="sh_golden_rdy",
            production_ready=True,
            metadata={"source": "golden"},
        )
    )

    md_transport = FakeLiveMdTransport(
        quotes={"AAPL": {"ap": 100.1, "bp": 99.9, "as": 50, "bs": 50, "t": "2020-06-01T15:00:00Z"}}
    )
    md = LiveMarketDataService(
        store,
        registry,
        transport=md_transport,
        artifact_store=LiveMdArtifactStore(root=tmp / "md_raw"),
    )
    md.connect()

    live_ad = fake_adapter(
        account={"id": ACCOUNT_ID, "cash": "5000", "equity": "5000"},
        positions=[{"symbol": "AAPL", "qty": "2", "avg_entry_price": "100"}],
    )
    live_ad.connect()
    lro = LiveReadonlyService(
        store,
        registry,
        adapter=live_ad,
        artifact_store=LiveReadonlyArtifactStore(root=tmp / "lro_raw"),
    )

    shadow = ShadowTradingService(
        store,
        registry,
        md=md,
        live_readonly=live_ad,
        artifact_store=ShadowArtifactStore(root=tmp / "shadow_raw"),
    )
    shadow.start_session(
        account_id=ACCOUNT_ID,
        dataset_hash=DATASET_HASH,
        model_version=MODEL_VERSION,
        strategy_version=STRATEGY_VERSION,
    )
    return store, registry, md, lro, shadow, live_ad
