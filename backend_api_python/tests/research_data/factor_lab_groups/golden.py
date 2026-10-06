"""人工 Golden：4 股精确分位收益 + 次日换手。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import EvaluationDatasetRecord
from app.services.research_data.factor_lab.groups import (
    CostModelSpec,
    FactorGroupEvaluationService,
    GroupSpec,
)
from app.services.research_data.factor_lab.groups.artifact_store import GroupArtifactStore
from app.services.research_data.registry import LocalJsonRegistry

EVAL_HASH = "eval_golden_4e"
D1 = date(2024, 5, 6)
D2 = date(2024, 5, 7)


def four_stock_panel() -> list[dict]:
    """D1: A4→4%, B3→3%, C2→2%, D1→1%；D2 成员变化便于 turnover。"""
    rows = []
    for ik, f, r in [
        ("CNStock:A", 4.0, 0.04),
        ("CNStock:B", 3.0, 0.03),
        ("CNStock:C", 2.0, 0.02),
        ("CNStock:D", 1.0, 0.01),
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
    # D2: 排序变化 A/B 掉出 top
    for ik, f, r in [
        ("CNStock:A", 1.0, 0.01),
        ("CNStock:B", 2.0, 0.02),
        ("CNStock:C", 3.0, 0.03),
        ("CNStock:D", 4.0, 0.04),
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


def tied_panel() -> list[dict]:
    return [
        {
            "instrument_key": f"CNStock:{x}",
            "factor_date": D1,
            "factor_value": f,
            "forward_return_1d": r,
            "sample_status": "VALID",
        }
        for x, f, r in [
            ("A", 1.0, 0.01),
            ("B", 1.0, 0.02),
            ("C", 1.0, 0.03),
            ("D", 2.0, 0.04),
        ]
    ]


def make_env(tmp_path: Path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    registry.upsert_evaluation_dataset(
        EvaluationDatasetRecord(
            evaluation_hash=EVAL_HASH,
            factor_dataset_id="fds_4e",
            factor_dataset_hash="ds_4e",
            snapshot_id="snap_4e",
            universe_code="CSI300",
            start_date=D1.isoformat(),
            end_date=D2.isoformat(),
            metadata={"direction": "POSITIVE"},
        )
    )
    svc = FactorGroupEvaluationService(
        store,
        registry,
        artifact_store=GroupArtifactStore(root=tmp_path / "group_art"),
    )
    return store, registry, svc


def default_spec(**kw) -> GroupSpec:
    """默认 2 组：4 股时 Q1={A,B} Q2={C,D}，LS=2%。"""
    base = dict(
        evaluation_hash=EVAL_HASH,
        group_count=2,
        direction="POSITIVE",
        horizons=[1, 5],
        min_cross_section_size=4,
        cost_model=CostModelSpec(kind="ZERO"),
    )
    base.update(kw)
    return GroupSpec(**base)
