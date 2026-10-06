"""人工 Golden：多日面板验 Rolling / Decay / Regime / look-ahead。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import EvaluationDatasetRecord
from app.services.research_data.factor_lab.metrics.protocol import MetricPoint
from app.services.research_data.factor_lab.stability import (
    FactorStabilityService,
    StabilitySpec,
)
from app.services.research_data.factor_lab.stability.artifact_store import (
    StabilityArtifactStore,
)
from app.services.research_data.registry import LocalJsonRegistry

EVAL_HASH = "eval_golden_4f"
START = date(2024, 1, 2)


def multi_day_panel(n_days: int = 15) -> list[dict]:
    """每日 4 股：factor 与 return 同序 → IC/RankIC ≈ 1；含 1d/5d。"""
    rows: list[dict] = []
    for i in range(n_days):
        d = START + timedelta(days=i)
        # 周末仍写日期（评价序列用日期序，不依赖交易日历）
        for ik, f, r in [
            ("CNStock:A", 4.0, 0.04),
            ("CNStock:B", 3.0, 0.03),
            ("CNStock:C", 2.0, 0.02),
            ("CNStock:D", 1.0, 0.01),
        ]:
            # 后半段略降收益，便于 decay / regime 区分
            scale = 1.0 if i < 8 else 0.5
            rows.append(
                {
                    "instrument_key": ik,
                    "factor_date": d,
                    "factor_value": f,
                    "forward_return_1d": r * scale,
                    "forward_return_5d": r * scale * 2,
                    "sample_status": "VALID",
                }
            )
    return rows


def cross_year_panel() -> list[dict]:
    """跨年少量日，验 YEAR regime。"""
    rows: list[dict] = []
    for d in (date(2023, 12, 29), date(2023, 12, 30), date(2024, 1, 2), date(2024, 1, 3)):
        for ik, f, r in [
            ("CNStock:A", 4.0, 0.04),
            ("CNStock:B", 3.0, 0.03),
            ("CNStock:C", 2.0, 0.02),
            ("CNStock:D", 1.0, 0.01),
        ]:
            rows.append(
                {
                    "instrument_key": ik,
                    "factor_date": d,
                    "factor_value": f,
                    "forward_return_1d": r,
                    "sample_status": "VALID",
                }
            )
    return rows


def make_metric_points(
    n_days: int = 12, *, ic_seq: list[float] | None = None
) -> list[MetricPoint]:
    """注入日度 IC，便于精确验 rolling / look-ahead。"""
    pts: list[MetricPoint] = []
    for i in range(n_days):
        d = START + timedelta(days=i)
        ic = float(ic_seq[i]) if ic_seq is not None else 0.05 + 0.001 * i
        pts.append(
            MetricPoint(
                evaluation_date=d,
                horizon=1,
                ic=ic,
                rank_ic=ic + 0.01,
                sample_count=4,
                valid=True,
            )
        )
    return pts


def make_env(tmp_path: Path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    registry.upsert_evaluation_dataset(
        EvaluationDatasetRecord(
            evaluation_hash=EVAL_HASH,
            factor_dataset_id="fds_4f",
            factor_dataset_hash="ds_4f",
            snapshot_id="snap_4f",
            universe_code="CSI300",
            start_date=START.isoformat(),
            end_date=(START + timedelta(days=20)).isoformat(),
            metadata={"direction": "POSITIVE"},
        )
    )
    svc = FactorStabilityService(
        store,
        registry,
        artifact_store=StabilityArtifactStore(root=tmp_path / "stab_art"),
    )
    return store, registry, svc


def default_spec(**kw) -> StabilitySpec:
    """测试默认：小窗口、小截面、2 组。"""
    base = dict(
        evaluation_hash=EVAL_HASH,
        rolling_windows=[3, 5],
        decay_horizons=[1, 5],
        regime_types=["YEAR", "QUARTER"],
        min_cross_section_size=4,
        min_rolling_samples=3,
        direction="POSITIVE",
        group_count=2,
    )
    base.update(kw)
    return StabilitySpec(**base)
