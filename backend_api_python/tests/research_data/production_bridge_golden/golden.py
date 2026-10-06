"""Phase 5F Golden：冻结 → 状态机 → 干跑 Inference。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import CrossValidationSummary
from app.services.research_data.production_bridge import (
    InferenceRequest,
    ProductionBridgeService,
)
from app.services.research_data.registry import LocalJsonRegistry

SHASH = "strat_hash_5f_golden_001"
SCODE = "momentum_5f_golden"
CVHASH = "cv_hash_5f_golden_001"
INST_A = "CNStock:600000"
INST_B = "CNStock:000001"


def make_env(tmp: Path):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    # 注入 CV PASSED
    registry.upsert_research_cross_validation(
        CrossValidationSummary(
            cv_hash=CVHASH,
            strategy_hash=SHASH,
            backtest_hash="bt_5f_golden",
            qlib_run_hash="ql_5f_golden",
            start_date="2020-01-02",
            end_date="2020-01-06",
            status="PASSED",
            execution_policy="NEXT_OPEN",
            realism="GROSS",
        )
    )
    svc = ProductionBridgeService(store, registry)
    return store, registry, svc


def trading_days(n: int = 3, start: date | None = None) -> list[date]:
    d0 = start or date(2020, 1, 2)
    return [d0 + timedelta(days=i) for i in range(n)]


def factor_rows(days: list[date]) -> list[dict[str, Any]]:
    rows = []
    for d in days:
        rows.append(
            {
                "instrument_key": INST_A,
                "trading_date": d.isoformat(),
                "score": 1.2,
                "target_weight": 0.6,
            }
        )
        rows.append(
            {
                "instrument_key": INST_B,
                "trading_date": d.isoformat(),
                "score": 0.8,
                "target_weight": 0.4,
            }
        )
    return rows


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


def freeze_meta(days: list[date] | None = None) -> dict[str, Any]:
    days = days or trading_days(3)
    return {
        "cv_hash": CVHASH,
        "strategy_code": SCODE,
        "universe_code": "CSI300_GOLDEN",
        "snapshot_id": "snap_5f_golden",
        "dataset_hash": "dh_5f",
        "allow_missing_strategy": True,
        "signal_definition_json": {"source": "FACTOR_DATASET"},
        "rebalance_rule_json": {"freq": "DAILY"},
        "holding_rule_json": {},
        "factor_rows": factor_rows(days),
        "offline_rows": factor_rows(days),
        "online_rows": factor_rows(days),
        "price_bars": price_bars(days),
        "universe_membership": [INST_A, INST_B],
        "force_recompute": True,
    }


def promote_to_deployed(svc: ProductionBridgeService, days: list[date] | None = None):
    """freeze → validate → promote → approve → deploy。"""
    meta = freeze_meta(days)
    r = svc.freeze(SHASH, metadata=meta)
    r = svc.validate(r.bundle_hash, metadata=meta)
    r = svc.promote(r.bundle_hash)
    r = svc.approve(r.bundle_hash)
    r = svc.deploy(r.bundle_hash)
    return r


def run_infer(svc: ProductionBridgeService, bundle_hash: str, day: date):
    days = [day]
    return svc.infer(
        InferenceRequest(bundle_hash=bundle_hash, trading_date=day),
        metadata={
            "factor_rows": factor_rows(days),
            "price_bars": price_bars(days),
            "universe_membership": [INST_A, INST_B],
            "max_single_weight": 1.0,
            "max_gross_exposure": 1.0,
        },
    )
