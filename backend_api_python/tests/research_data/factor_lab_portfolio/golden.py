"""Golden：因子截面 → Long-only / Long-short / Quantile 组合。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import FactorDatasetRecord
from app.services.research_data.factor_lab.portfolio import (
    FactorPortfolioService,
    PortfolioSpec,
)
from app.services.research_data.factor_lab.portfolio.artifact_store import (
    PortfolioArtifactStore,
)
from app.services.research_data.registry import LocalJsonRegistry

FID = "fds_port_4i"
EHASH = "eval_port_4i"
D0 = date(2024, 8, 5)  # Monday


def _ik(i: int) -> str:
    return f"CNStock:{i:03d}"


def factor_panel(
    n: int = 40, days: int = 10, *, start: date | None = None
) -> list[dict]:
    """递增因子；多日保持同序（便于调仓测试）。"""
    start = start or D0
    rows: list[dict] = []
    for d_off in range(days):
        d = start + timedelta(days=d_off)
        # 跳过周末，保证 WEEKLY 有跨周工作日
        if d.weekday() >= 5:
            continue
        for i in range(n):
            rows.append(
                {
                    "instrument_key": _ik(i),
                    "trading_date": d,
                    "value": float(i) + 0.01 * d_off,
                }
            )
    return rows


def evaluation_panel(
    factor_rows: list[dict], *, horizon: int = 1
) -> list[dict]:
    """forward_return 与因子同向（高因子高收益）。"""
    col = f"forward_return_{horizon}d"
    out: list[dict] = []
    for r in factor_rows:
        v = float(r["value"])
        out.append(
            {
                "instrument_key": r["instrument_key"],
                "factor_date": r["trading_date"],
                "factor_value": v,
                "sample_status": "VALID",
                col: v * 0.001,
            }
        )
    return out


def make_env(tmp_path: Path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    registry.upsert_factor_dataset(
        FactorDatasetRecord(
            factor_dataset_id=FID,
            factor_ref="raw_port@1.0.0",
            factor_hash="fh_4i",
            dataset_hash="dh_4i",
            snapshot_id="snap_4i",
            universe_code="CSI300",
            start_date=D0.isoformat(),
            end_date=(D0 + timedelta(days=30)).isoformat(),
            row_count=0,
            layout="long",
        )
    )
    svc = FactorPortfolioService(
        store,
        registry,
        artifact_store=PortfolioArtifactStore(root=tmp_path / "port_art"),
    )
    return store, registry, svc


def default_spec(**kw) -> PortfolioSpec:
    base = dict(
        factor_dataset_id=FID,
        evaluation_hash=EHASH,
        construction_method="LONG_ONLY",
        weight_method="EQUAL_WEIGHT",
        selection_mode="TOP_PCT",
        top_pct=0.1,
        rebalance_frequency="DAILY",
        horizon=1,
        min_turnover=0.0,
        min_cross_section_size=10,
        direction="POSITIVE",
    )
    base.update(kw)
    return PortfolioSpec(**base)


def run_portfolio(
    svc: FactorPortfolioService,
    factor_rows: list[dict],
    eval_rows: list[dict],
    spec: PortfolioSpec | None = None,
    **meta,
):
    return svc.run(
        FID,
        spec or default_spec(),
        metadata={
            "factor_records": factor_rows,
            "evaluation_records": eval_rows,
            "force_recompute": True,
            **meta,
        },
    )
