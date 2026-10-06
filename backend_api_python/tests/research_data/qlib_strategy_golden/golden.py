"""Phase 5D Golden：Signal/Weight 适配 + compatibility（无 pyqlib）。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.qlib_strategy import (
    QlibStrategyService,
    QlibStrategySpec,
)
from app.services.research_data.research_backtest.protocol import (
    ResearchExecutionPolicy,
)

SHASH = "strat_hash_5d_golden_001"
INST_A = "CNStock:600000"
INST_B = "CNStock:000001"


def make_env(tmp: Path):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    svc = QlibStrategyService(store, registry, qlib_adapter=None)
    return store, registry, svc


def trading_days(n: int = 4, start: date | None = None) -> list[date]:
    d0 = start or date(2020, 1, 2)
    return [d0 + timedelta(days=i) for i in range(n)]


def signal_rows(days: list[date]) -> list[dict[str, Any]]:
    rows = []
    for d in days:
        rows.append(
            {
                "instrument_key": INST_A,
                "trading_date": d.isoformat(),
                "score": 1.5,
            }
        )
        rows.append(
            {
                "instrument_key": INST_B,
                "trading_date": d.isoformat(),
                "score": -0.5,
            }
        )
    return rows


def targets_by_date(days: list[date]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for d in days:
        out[d.isoformat()] = [
            {"instrument_key": INST_A, "target_weight": 0.6},
            {"instrument_key": INST_B, "target_weight": 0.4},
        ]
    return out


def price_bars(days: list[date]) -> list[dict[str, Any]]:
    rows = []
    for i, d in enumerate(days):
        rows.append(
            {
                "instrument_key": INST_A,
                "trading_date": d.isoformat(),
                "open": 10.0 + i * 0.1,
                "close": 10.1 + i * 0.1,
            }
        )
        rows.append(
            {
                "instrument_key": INST_B,
                "trading_date": d.isoformat(),
                "open": 20.0 + i * 0.05,
                "close": 20.05 + i * 0.05,
            }
        )
    return rows


def default_spec(
    days: list[date] | None = None,
    *,
    realism: str = "GROSS",
) -> QlibStrategySpec:
    days = days or trading_days(4)
    return QlibStrategySpec(
        strategy_hash=SHASH,
        start_date=days[0],
        end_date=days[-1],
        execution_policy=ResearchExecutionPolicy(mode="NEXT_OPEN"),
        realism=realism,  # type: ignore[arg-type]
        market_rule="CN_A",
        initial_nav=1.0,
        dataset_ref="mock_ds@1",
        materialization_id="mat_injected_5d",
        dataset_hash="dh_5d",
    )


def run_adapter(
    svc: QlibStrategyService,
    *,
    realism: str = "GROSS",
    days: list[date] | None = None,
):
    days = days or trading_days(4)
    spec = default_spec(days, realism=realism)
    meta = {
        "targets_by_date": targets_by_date(days[:3]),
        "signal_rows": signal_rows(days[:3]),
        "price_bars": price_bars(days),
        "skip_ensure_cache": True,
        "materialization_id": "mat_injected_5d",
        "dataset_hash": "dh_5d",
        "force_recompute": True,
        "force_inprocess": True,
        "force_synthetic": True,
    }
    return svc.run(SHASH, spec, metadata=meta)
