"""Golden：Factor + 注入 4I 持仓 → Strategy Contract。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import (
    FactorDatasetRecord,
    FactorPortfolioSummary,
)
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.strategy_research import (
    HoldingRule,
    RebalanceRule,
    SignalDefinition,
    StrategyResearchService,
    StrategySpec,
)
from app.services.research_data.strategy_research.artifact_store import (
    StrategyArtifactStore,
)

FID = "fds_strat_5a"
PHASH = "port_hash_5a_test0001"
CODE = "mom_top_weekly"
D0 = date(2024, 9, 2)  # Monday


def _ik(i: int) -> str:
    return f"CNStock:{i:03d}"


def factor_panel(n: int = 20, days: int = 3) -> list[dict]:
    rows: list[dict] = []
    for d_off in range(days):
        d = D0 + timedelta(days=d_off)
        if d.weekday() >= 5:
            continue
        for i in range(n):
            # 含正负分，便于 SIGN_OF_SCORE
            rows.append(
                {
                    "instrument_key": _ik(i),
                    "trading_date": d,
                    "value": float(i - n // 2),
                }
            )
    return rows


def portfolio_positions(n: int = 20, days: int = 3, top: int = 4) -> list[dict]:
    """模拟 4I LONG_ONLY top 持仓。"""
    rows: list[dict] = []
    for d_off in range(days):
        d = D0 + timedelta(days=d_off)
        if d.weekday() >= 5:
            continue
        chosen = list(range(n - top, n))
        w = 1.0 / top
        for i in chosen:
            rows.append(
                {
                    "instrument_key": _ik(i),
                    "trading_date": d.isoformat(),
                    "target_weight": w,
                    "leg": "LONG",
                }
            )
    return rows


def make_env(tmp_path: Path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    registry.upsert_factor_dataset(
        FactorDatasetRecord(
            factor_dataset_id=FID,
            factor_ref="raw_strat@1.0.0",
            factor_hash="fh_5a",
            dataset_hash="dh_5a",
            snapshot_id="snap_5a",
            universe_code="CSI300",
            start_date=D0.isoformat(),
            end_date=(D0 + timedelta(days=10)).isoformat(),
            row_count=0,
            layout="long",
        )
    )
    registry.upsert_factor_portfolio(
        FactorPortfolioSummary(
            portfolio_hash=PHASH,
            factor_dataset_id=FID,
            evaluation_hash="eval_5a",
            construction_method="LONG_ONLY",
            weight_method="EQUAL_WEIGHT",
            rebalance_frequency="DAILY",
        )
    )
    svc = StrategyResearchService(
        store,
        registry,
        artifact_store=StrategyArtifactStore(root=tmp_path / "strat_art"),
    )
    return store, registry, svc


def default_spec(**kw) -> StrategySpec:
    base = dict(
        strategy_code=CODE,
        strategy_name="Momentum Top",
        factor_dataset_id=FID,
        portfolio_hash=PHASH,
        signal_definition=SignalDefinition(factor_dataset_id=FID),
        rebalance_rule=RebalanceRule(frequency="DAILY"),
        holding_rule=HoldingRule(),
        universe_code="CSI300",
        snapshot_id="snap_5a",
    )
    base.update(kw)
    return StrategySpec(**base)


def run_materialize(svc, factors, positions, spec=None, **meta):
    return svc.materialize(
        CODE if spec is None else spec.strategy_code,
        spec or default_spec(),
        metadata={
            "factor_records": factors,
            "portfolio_positions": positions,
            "force_recompute": True,
            **meta,
        },
    )
