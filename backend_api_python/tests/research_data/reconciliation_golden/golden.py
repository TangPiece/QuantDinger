"""Phase 6F Golden：OMS/Portfolio vs BrokerSnapshot 对账。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.broker_adapter import BrokerAdapterService, SimulatedBrokerAdapter
from app.services.broker_adapter.raw_store import BrokerRawStore
from app.services.oms import OMSService
from app.services.portfolio_service import PortfolioService
from app.services.reconciliation_service import ReconciliationService
from app.services.reconciliation_service.artifact_store import (
    ReconciliationArtifactStore,
)
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import OrderIntent
from app.services.research_data.registry import LocalJsonRegistry

INST_A = "USStock:AAPL"
DAY = date(2020, 1, 2)


def prices() -> dict[str, float]:
    return {INST_A: 100.0}


def sample_intent(*, qty: float = 10.0, reason: str = "recon", **kwargs) -> OrderIntent:
    return OrderIntent(
        instrument_key=INST_A,
        side="BUY",
        quantity=float(qty),
        urgency="NORMAL",
        execution_algorithm=str(kwargs.get("algo") or "MARKET"),  # type: ignore[arg-type]
        limit_price=kwargs.get("limit_price"),
        reason=reason,
        trading_date=DAY.isoformat(),
    )


def make_env(tmp: Path):
    """SANDBOX Simulated + OMS + Portfolio + Reconciliation（Gate 已接线）。"""
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    portfolio = PortfolioService(store, registry)
    adapter = SimulatedBrokerAdapter(execution_mode="SANDBOX", prices=prices())
    adapter.connect()
    raw = BrokerRawStore(root=tmp / "broker_raw")
    broker_svc = BrokerAdapterService(
        store, registry, adapter=adapter, raw_store=raw
    )
    oms = OMSService(
        store,
        registry,
        portfolio_service=portfolio,
        broker_port=adapter,
        broker_adapter_service=broker_svc,
    )
    recon = ReconciliationService(
        store,
        registry,
        portfolio_service=portfolio,
        oms_service=oms,
        broker_adapter_service=broker_svc,
        broker_adapter=adapter,
        artifact_store=ReconciliationArtifactStore(root=tmp / "recon_raw"),
    )
    oms.set_trading_gate(recon.gate)
    return store, registry, portfolio, oms, recon, adapter, broker_svc
