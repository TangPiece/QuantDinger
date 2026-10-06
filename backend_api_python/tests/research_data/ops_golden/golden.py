"""Phase 6H Golden：Ops + OMS + Safety + Reconciliation 接线。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.broker_adapter import BrokerAdapterService, SimulatedBrokerAdapter
from app.services.broker_adapter.raw_store import BrokerRawStore
from app.services.oms import OMSService
from app.services.ops_service import OpsService
from app.services.ops_service.artifact_store import OpsArtifactStore
from app.services.ops_service.trace import ensure_trace_id
from app.services.portfolio_service import PortfolioService
from app.services.reconciliation_service import ReconciliationService
from app.services.reconciliation_service.artifact_store import (
    ReconciliationArtifactStore,
)
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import OrderIntent
from app.services.research_data.registry import LocalJsonRegistry
from app.services.safety_service import SafetyService
from app.services.safety_service.artifact_store import SafetyArtifactStore
from app.services.safety_service.sources import InMemoryBrokerConnectivity

INST_A = "USStock:AAPL"
DAY = date(2020, 1, 2)


def prices() -> dict[str, float]:
    return {INST_A: 100.0}


def sample_intent(*, qty: float = 10.0, reason: str = "ops", **kwargs) -> OrderIntent:
    intent = OrderIntent(
        instrument_key=INST_A,
        side="BUY",
        quantity=float(qty),
        urgency="NORMAL",
        execution_algorithm=str(kwargs.get("algo") or "MARKET"),  # type: ignore[arg-type]
        limit_price=kwargs.get("limit_price"),
        reason=reason,
        trading_date=DAY.isoformat(),
    )
    ensure_trace_id(intent, seed=reason)
    return intent


def make_env(tmp: Path):
    """全链路 + OpsService 钩子。"""
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    portfolio = PortfolioService(store, registry)
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
    return store, registry, portfolio, oms, safety, recon, ops, adapter, broker_conn
