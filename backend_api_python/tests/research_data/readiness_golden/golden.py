"""Phase 6J Golden：6B–6I + ReadinessService 接线。"""

from __future__ import annotations

from pathlib import Path

from app.services.broker_adapter import BrokerAdapterService, SimulatedBrokerAdapter
from app.services.broker_adapter.raw_store import BrokerRawStore
from app.services.e2e_service import E2EService
from app.services.e2e_service.artifact_store import E2EArtifactStore
from app.services.oms import OMSService
from app.services.ops_service import OpsService
from app.services.ops_service.artifact_store import OpsArtifactStore
from app.services.portfolio_service import PortfolioService
from app.services.production_readiness import ReadinessService
from app.services.production_readiness.artifact_store import ReadinessArtifactStore
from app.services.reconciliation_service import ReconciliationService
from app.services.reconciliation_service.artifact_store import (
    ReconciliationArtifactStore,
)
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.registry import LocalJsonRegistry
from app.services.risk_engine import RiskEngineService
from app.services.risk_engine.policy import finalize_policy
from app.services.risk_engine.protocol import RiskPolicy
from app.services.safety_service import SafetyService
from app.services.safety_service.artifact_store import SafetyArtifactStore
from app.services.safety_service.sources import InMemoryBrokerConnectivity

INST_A = "USStock:AAPL"
DATASET_HASH = "rdy_dh_v1"
STRATEGY_VERSION = "rdy_sv_v1"


def prices() -> dict[str, float]:
    return {INST_A: 100.0}


def default_policy(**overrides) -> RiskPolicy:
    p = RiskPolicy(
        policy_code="rdy_golden",
        policy_version="1",
        max_single_position_weight=0.50,
        max_gross_exposure=1.0,
        max_turnover=1.0,
        max_position_delta_weight=0.50,
        clip_on_limit=True,
    )
    if overrides:
        p = p.model_copy(update=overrides)
    return finalize_policy(p)


def make_env(tmp: Path):
    """全链路 + ReadinessService（与 e2e_golden 同构）。"""
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    registry_root = cache / "registry"
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=registry_root)
    portfolio = PortfolioService(store, registry)
    risk = RiskEngineService(store, registry)
    risk.register_policy(default_policy())
    broker_conn = InMemoryBrokerConnectivity(connected=True)
    adapter = SimulatedBrokerAdapter(execution_mode="SANDBOX", prices=prices())
    adapter.connect()
    raw = BrokerRawStore(root=tmp / "broker_raw")
    broker_svc = BrokerAdapterService(
        store, registry, adapter=adapter, raw_store=raw
    )
    ops = OpsService(
        registry,
        artifact_store=OpsArtifactStore(root=tmp / "ops_raw"),
        broker_port=broker_conn,
    )
    ops.seed_default_rules()
    oms = OMSService(
        store,
        registry,
        portfolio_service=portfolio,
        broker_port=adapter,
        broker_adapter_service=broker_svc,
        ops_service=ops,
    )
    safety = SafetyService(
        store,
        registry,
        portfolio_service=portfolio,
        oms_service=oms,
        artifact_store=SafetyArtifactStore(root=tmp / "safety_raw"),
        broker_port=broker_conn,
        ops_service=ops,
    )
    ops.set_safety_service(safety)
    oms.set_trading_gate(safety.gate)
    recon = ReconciliationService(
        store,
        registry,
        portfolio_service=portfolio,
        oms_service=oms,
        broker_adapter_service=broker_svc,
        broker_adapter=adapter,
        artifact_store=ReconciliationArtifactStore(root=tmp / "recon_raw"),
        safety_service=safety,
        ops_service=ops,
    )
    e2e = E2EService(
        store,
        registry,
        portfolio_service=portfolio,
        risk_service=risk,
        oms_service=oms,
        safety_service=safety,
        recon_service=recon,
        ops_service=ops,
        artifact_store=E2EArtifactStore(root=tmp / "e2e_raw"),
        default_policy=default_policy(),
        prices=prices(),
        broker_adapter=adapter,
        broker_conn=broker_conn,
    )
    rdy = ReadinessService(
        store,
        registry,
        portfolio_service=portfolio,
        risk_service=risk,
        oms_service=oms,
        safety_service=safety,
        recon_service=recon,
        ops_service=ops,
        e2e_service=e2e,
        broker_adapter=adapter,
        broker_adapter_service=broker_svc,
        artifact_store=ReadinessArtifactStore(root=tmp / "rdy_raw"),
        prices=prices(),
        registry_root=registry_root,
    )
    return (
        store,
        registry,
        portfolio,
        risk,
        oms,
        safety,
        recon,
        ops,
        adapter,
        broker_conn,
        e2e,
        rdy,
    )
