"""Phase 6B Golden：Account → Target → Delta → Paper Fill → Snapshot。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.services.portfolio_service import PortfolioService
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import TargetPosition
from app.services.research_data.registry import LocalJsonRegistry

INST_A = "CNStock:600000"
INST_B = "CNStock:000001"
DAY = date(2020, 1, 2)


def make_env(tmp: Path):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    svc = PortfolioService(store, registry)
    return store, registry, svc


def prices(day: date | None = None) -> dict[str, float]:
    return {INST_A: 10.0, INST_B: 20.0}


def price_bars(day: date | None = None) -> list[dict[str, Any]]:
    d = (day or DAY).isoformat()
    return [
        {"instrument_key": INST_A, "trading_date": d, "open": 10.0, "close": 10.0},
        {"instrument_key": INST_B, "trading_date": d, "open": 20.0, "close": 20.0},
    ]


def targets(
    day: date | None = None,
    *,
    w_a: float = 0.4,
    w_b: float = 0.3,
) -> list[TargetPosition]:
    d = day or DAY
    ts = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
    return [
        TargetPosition(
            instrument_key=INST_A,
            trading_date=d.isoformat(),
            portfolio_id="pf_golden",
            strategy_version="v1",
            dataset_hash="dh",
            timestamp=ts,
            target_weight=w_a,
        ),
        TargetPosition(
            instrument_key=INST_B,
            trading_date=d.isoformat(),
            portfolio_id="pf_golden",
            strategy_version="v1",
            dataset_hash="dh",
            timestamp=ts,
            target_weight=w_b,
        ),
    ]
