"""人工可验算 Golden：正相关 / 负相关 / RankIC±1 / 边界。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import EvaluationDatasetRecord
from app.services.research_data.factor_lab.metrics import (
    FactorMetricsService,
    MetricSpec,
)
from app.services.research_data.factor_lab.metrics.artifact_store import MetricArtifactStore
from app.services.research_data.registry import LocalJsonRegistry

EVAL_HASH = "eval_golden_4d"
D1 = date(2024, 5, 6)
D2 = date(2024, 5, 7)
D3 = date(2024, 5, 8)


def perfect_rank_panel() -> list[dict]:
    """D1 RankIC=1；D2 RankIC=-1；含 1d/5d 两 horizon。"""
    rows = []
    # Day1: factor 与 return 同序
    for ik, f, r in [
        ("CNStock:A", 1.0, 0.01),
        ("CNStock:B", 2.0, 0.02),
        ("CNStock:C", 3.0, 0.03),
    ]:
        rows.append(
            {
                "instrument_key": ik,
                "factor_date": D1,
                "factor_value": f,
                "forward_return_1d": r,
                "forward_return_5d": r * 2,
                "sample_status": "VALID",
            }
        )
    # Day2: 完全反序
    for ik, f, r in [
        ("CNStock:A", 3.0, 0.01),
        ("CNStock:B", 2.0, 0.02),
        ("CNStock:C", 1.0, 0.03),
    ]:
        rows.append(
            {
                "instrument_key": ik,
                "factor_date": D2,
                "factor_value": f,
                "forward_return_1d": r,
                "forward_return_5d": r * 2,
                "sample_status": "VALID",
            }
        )
    return rows


def constant_factor_panel() -> list[dict]:
    return [
        {
            "instrument_key": f"CNStock:{i}",
            "factor_date": D1,
            "factor_value": 1.0,
            "forward_return_1d": 0.01 * (i + 1),
            "sample_status": "VALID",
        }
        for i in range(5)
    ]


def constant_return_panel() -> list[dict]:
    return [
        {
            "instrument_key": f"CNStock:{i}",
            "factor_date": D1,
            "factor_value": float(i),
            "forward_return_1d": 0.02,
            "sample_status": "VALID",
        }
        for i in range(5)
    ]


def tiny_panel() -> list[dict]:
    """仅 2 只股票，低于默认 min=30。"""
    return [
        {
            "instrument_key": "CNStock:A",
            "factor_date": D1,
            "factor_value": 1.0,
            "forward_return_1d": 0.01,
            "sample_status": "VALID",
        },
        {
            "instrument_key": "CNStock:B",
            "factor_date": D1,
            "factor_value": 2.0,
            "forward_return_1d": 0.02,
            "sample_status": "VALID",
        },
    ]


def with_missing_panel() -> list[dict]:
    rows = perfect_rank_panel()
    rows.append(
        {
            "instrument_key": "CNStock:D",
            "factor_date": D1,
            "factor_value": float("nan"),
            "forward_return_1d": 0.05,
            "sample_status": "MISSING_FACTOR",
        }
    )
    rows.append(
        {
            "instrument_key": "CNStock:E",
            "factor_date": D1,
            "factor_value": 9.0,
            "forward_return_1d": None,
            "sample_status": "MISSING_RETURN",
        }
    )
    return rows


def make_env(tmp_path: Path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    registry.upsert_evaluation_dataset(
        EvaluationDatasetRecord(
            evaluation_hash=EVAL_HASH,
            factor_dataset_id="fds_4d",
            factor_dataset_hash="ds_4d",
            snapshot_id="snap_4d",
            universe_code="CSI300",
            start_date=D1.isoformat(),
            end_date=D2.isoformat(),
            return_spec={"horizons": [1, 5]},
        )
    )
    svc = FactorMetricsService(
        store,
        registry,
        artifact_store=MetricArtifactStore(root=tmp_path / "metric_art"),
    )
    return store, registry, svc


def default_spec(**kw) -> MetricSpec:
    base = dict(
        evaluation_hash=EVAL_HASH,
        horizons=[1, 5],
        min_cross_section_size=3,
        direction="AUTO",
    )
    base.update(kw)
    return MetricSpec(**base)
