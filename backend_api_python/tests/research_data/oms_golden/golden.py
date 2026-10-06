"""Phase 6D Golden：OrderIntent → OMS → Paper → Fill → Position。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.oms import OMSService
from app.services.oms.artifact_store import OmsArtifactStore
from app.services.oms.paper_broker import PaperBroker
from app.services.portfolio_service import PortfolioService
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import OrderIntent
from app.services.research_data.registry import LocalJsonRegistry
from app.services.risk_engine import RiskEngineService, RiskPolicy
from app.services.risk_engine.policy import finalize_policy

INST_A = "CNStock:600000"
INST_B = "CNStock:000001"
DAY = date(2020, 1, 2)


def make_env(tmp: Path):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    portfolio = PortfolioService(store, registry)
    risk = RiskEngineService(store, registry)
    artifacts = OmsArtifactStore(root=tmp / "oms_artifacts")
    oms = OMSService(
        store,
        registry,
        portfolio_service=portfolio,
        paper_broker=PaperBroker(prices=prices()),
        artifact_store=artifacts,
    )
    return store, registry, portfolio, risk, oms


def prices() -> dict[str, float]:
    return {INST_A: 10.0, INST_B: 20.0}


def sample_intent(
    *,
    side: str = "BUY",
    qty: float = 100.0,
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


def default_policy(**overrides) -> RiskPolicy:
    p = RiskPolicy(
        policy_code="oms_golden",
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
