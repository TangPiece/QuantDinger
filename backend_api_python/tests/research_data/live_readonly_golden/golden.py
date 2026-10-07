"""Phase 7A Golden：LiveReadonlyService + 6F Recon（Fake transport）。"""

from __future__ import annotations

import os
from pathlib import Path

from app.services.live_readonly.adapter import fake_adapter
from app.services.live_readonly.artifact_store import LiveReadonlyArtifactStore
from app.services.live_readonly.runner import LiveReadonlyService
from app.services.oms import OMSService
from app.services.ops_service import OpsService
from app.services.ops_service.artifact_store import OpsArtifactStore
from app.services.portfolio_service import PortfolioService
from app.services.reconciliation_service import ReconciliationService
from app.services.reconciliation_service.artifact_store import (
    ReconciliationArtifactStore,
)
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import ReadinessRunSummary
from app.services.research_data.registry import LocalJsonRegistry

DATASET_HASH = "lro_dh_v1"
MODEL_VERSION = "lro_mv_v1"
STRATEGY_VERSION = "lro_sv_v1"
ACCOUNT_ID = "fake-live-acct"


def make_env(tmp: Path):
    """构造只读 Live 测试环境；默认 PRODUCTION_READY=true。"""
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    registry_root = cache / "registry"
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=registry_root)
    os.environ["PRODUCTION_READY"] = "true"
    registry.upsert_readiness_run(
        ReadinessRunSummary(
            run_id="lro_golden_rdy",
            production_ready=True,
            metadata={"source": "golden"},
        )
    )

    portfolio = PortfolioService(store, registry)
    ops = OpsService(
        registry,
        artifact_store=OpsArtifactStore(root=tmp / "ops_raw"),
    )
    ops.seed_default_rules()

    from app.services.broker_adapter import SimulatedBrokerAdapter

    paper_adapter = SimulatedBrokerAdapter(
        execution_mode="SANDBOX", prices={"USStock:AAPL": 100.0}
    )
    paper_adapter.connect()

    oms = OMSService(
        store,
        registry,
        portfolio_service=portfolio,
        broker_port=paper_adapter,
        ops_service=ops,
    )

    live_ad = fake_adapter(
        account={"id": ACCOUNT_ID, "cash": "5000", "equity": "5000", "buying_power": "5000"},
        positions=[{"symbol": "AAPL", "qty": "1", "avg_entry_price": "100", "market_value": "100"}],
    )
    live_ad.connect()

    recon = ReconciliationService(
        store,
        registry,
        portfolio_service=portfolio,
        oms_service=oms,
        broker_adapter=paper_adapter,
        artifact_store=ReconciliationArtifactStore(root=tmp / "recon_raw"),
        ops_service=ops,
    )

    lro = LiveReadonlyService(
        store,
        registry,
        adapter=live_ad,
        recon_service=recon,
        ops_service=ops,
        artifact_store=LiveReadonlyArtifactStore(root=tmp / "lro_raw"),
    )
    # 7B 阶梯：PAPER → SHADOW → LIVE_READONLY
    lro.set_environment("SHADOW", account_id=ACCOUNT_ID, actor="golden")
    lro.set_environment("LIVE_READONLY", account_id=ACCOUNT_ID, actor="golden")
    return store, registry, portfolio, oms, recon, ops, live_ad, lro
