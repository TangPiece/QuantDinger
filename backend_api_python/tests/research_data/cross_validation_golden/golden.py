"""Phase 5E Golden：同一注入 TargetPosition / bars 双引擎交叉验证。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.cross_validation import (
    CrossValidationService,
    CrossValidationSpec,
    Tolerances,
)
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.research_backtest.protocol import (
    ResearchExecutionPolicy,
)

SHASH = "strat_hash_5e_golden_001"
INST_A = "CNStock:600000"
INST_B = "CNStock:000001"


def make_env(tmp: Path):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    svc = CrossValidationService(store, registry)
    return store, registry, svc


def trading_days(n: int = 5, start: date | None = None) -> list[date]:
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
) -> CrossValidationSpec:
    days = days or trading_days(5)
    return CrossValidationSpec(
        strategy_hash=SHASH,
        start_date=days[0],
        end_date=days[-1],
        execution_policy=ResearchExecutionPolicy(mode="NEXT_OPEN"),
        realism=realism,  # type: ignore[arg-type]
        market_rule="CN_A",
        initial_nav=1.0,
        # 合成 Qlib vs QD NEXT_OPEN：放宽 NAV/Perf 容差
        tolerances=Tolerances(
            signal_abs=1e-8,
            weight_abs=1e-8,
            nav_abs=0.08,
            nav_rel=0.08,
            perf_abs=0.08,
            other_abs=0.1,
        ),
    )


def run_cv(
    svc: CrossValidationService,
    *,
    realism: str = "GROSS",
    days: list[date] | None = None,
):
    days = days or trading_days(5)
    spec = default_spec(days, realism=realism)
    membership = [INST_A, INST_B]
    meta = {
        "targets_by_date": targets_by_date(days[:4]),
        "signal_rows": signal_rows(days[:4]),
        "price_bars": price_bars(days),
        "universe_membership": membership,
        "universe_code": "CSI300_GOLDEN",
        "snapshot_id": "snap_5e_golden",
        "dataset_ref": "mock_ds@1",
        "materialization_id": "mat_injected_5e",
        "dataset_hash": "dh_5e",
        "force_recompute": True,
        "force_synthetic": True,
        "force_inprocess": True,
        "skip_ensure_cache": True,
    }
    return svc.run(SHASH, spec, metadata=meta)
