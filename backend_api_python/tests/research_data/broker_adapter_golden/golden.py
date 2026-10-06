"""Phase 6E Golden：OMS ↔ BrokerAdapter ↔ Fake / Paper。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.broker_adapter import (
    BrokerAdapterService,
    PaperBrokerAdapter,
    SimulatedBrokerAdapter,
)
from app.services.broker_adapter.raw_store import BrokerRawStore
from app.services.oms import OMSService
from app.services.oms.artifact_store import OmsArtifactStore
from app.services.portfolio_service import PortfolioService
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import OrderIntent
from app.services.research_data.registry import LocalJsonRegistry
from app.services.risk_engine import RiskEngineService

INST_A = "USStock:AAPL"
INST_B = "USStock:MSFT"
DAY = date(2020, 1, 2)


def prices() -> dict[str, float]:
    return {INST_A: 100.0, INST_B: 200.0}


def make_env(tmp: Path, *, mode: str = "PAPER"):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    portfolio = PortfolioService(store, registry)
    risk = RiskEngineService(store, registry)
    raw = BrokerRawStore(root=tmp / "broker_raw")
    if mode in ("SANDBOX", "SHADOW"):
        adapter = SimulatedBrokerAdapter(
            execution_mode=mode, prices=prices()  # type: ignore[arg-type]
        )
        adapter.connect()
        broker_svc = BrokerAdapterService(
            store, registry, adapter=adapter, raw_store=raw
        )
        port = adapter
    else:
        adapter = PaperBrokerAdapter(prices=prices())
        adapter.connect()
        broker_svc = BrokerAdapterService(
            store, registry, adapter=adapter, raw_store=raw
        )
        port = adapter
    oms = OMSService(
        store,
        registry,
        portfolio_service=portfolio,
        broker_port=port,
        broker_adapter_service=broker_svc,
        artifact_store=OmsArtifactStore(root=tmp / "oms_artifacts"),
    )
    return store, registry, portfolio, risk, oms, broker_svc, adapter


def sample_intent(
    *,
    side: str = "BUY",
    qty: float = 10.0,
    algo: str = "MARKET",
    limit_price: float | None = None,
    reason: str = "golden",
    instrument: str = INST_A,
) -> OrderIntent:
    return OrderIntent(
        instrument_key=instrument,
        side=side,  # type: ignore[arg-type]
        quantity=qty,
        urgency="NORMAL",
        execution_algorithm=algo,  # type: ignore[arg-type]
        limit_price=limit_price,
        trading_date=DAY.isoformat(),
        reason=reason,
    )
