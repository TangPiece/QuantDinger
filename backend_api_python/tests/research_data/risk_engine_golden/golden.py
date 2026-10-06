"""Phase 6C Golden：PositionDelta → Risk → OrderIntent。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.services.portfolio_service import PortfolioService
from app.services.portfolio_service.protocol import PositionDelta
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import TargetPosition
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
    return store, registry, portfolio, risk


def default_policy(**overrides) -> RiskPolicy:
    p = RiskPolicy(
        policy_code="golden",
        policy_version="1",
        max_single_position_weight=0.10,
        max_gross_exposure=1.0,
        max_turnover=0.50,
        max_position_delta_weight=0.20,
        clip_on_limit=True,
        require_universe=False,
        short_allowed=False,
    )
    if overrides:
        p = p.model_copy(update=overrides)
    return finalize_policy(p)


def prices() -> dict[str, float]:
    return {INST_A: 10.0, INST_B: 20.0}


def targets(w_a: float = 0.08, w_b: float = 0.05) -> list[TargetPosition]:
    ts = datetime(2020, 1, 2, 10, 0, tzinfo=timezone.utc)
    return [
        TargetPosition(
            instrument_key=INST_A,
            trading_date=DAY.isoformat(),
            portfolio_id="pf",
            strategy_version="v1",
            dataset_hash="dh",
            timestamp=ts,
            target_weight=w_a,
        ),
        TargetPosition(
            instrument_key=INST_B,
            trading_date=DAY.isoformat(),
            portfolio_id="pf",
            strategy_version="v1",
            dataset_hash="dh",
            timestamp=ts,
            target_weight=w_b,
        ),
    ]


def sample_deltas(
    *,
    tw_a: float = 0.15,
    cw_a: float = 0.0,
    equity: float = 1_000_000.0,
) -> list[PositionDelta]:
    px = prices()[INST_A]
    tq = (tw_a * equity) / px
    cq = (cw_a * equity) / px
    dq = tq - cq
    return [
        PositionDelta(
            instrument_key=INST_A,
            current_weight=cw_a,
            target_weight=tw_a,
            delta_weight=tw_a - cw_a,
            current_quantity=cq,
            target_quantity=tq,
            delta_quantity=dq,
            side="BUY" if dq > 0 else ("SELL" if dq < 0 else "FLAT"),
            notional=abs(dq) * px,
        )
    ]
