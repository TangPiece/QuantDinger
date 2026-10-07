"""Phase 8H：Production → Research Feedback Loop 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.production_research_feedback.protocol import ENGINE_VERSION
from app.services.production_research_feedback.runner import ProductionResearchFeedbackError
from app.services.production_research_feedback.hashing import compute_feedback_dataset_hash

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_research_feedback_golden.golden import (  # noqa: E402
    STRATEGY_CODE,
    golden_bad_pit_lineage_inject,
    golden_production_feedback_inject,
    make_feedback_env,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_production_research_feedback@1"


def test_fake_inject_dataset_snapshot_failure_case(tmp_path):
    svc, _reg, dq = make_feedback_env(tmp_path / "flow")
    inj = golden_production_feedback_inject()
    ds = svc.build_dataset(
        STRATEGY_CODE,
        "PERFORMANCE_FEEDBACK",
        "2025-05-01",
        "2025-06-01",
        inject=inj,
        session_id="h1",
    )
    assert ds.dataset_hash
    snap = svc.build_reality_snapshot(
        STRATEGY_CODE,
        dataset_id=ds.dataset_id,
        inject=inj,
        session_id="h1",
    )
    case = svc.record_failure_case(
        STRATEGY_CODE,
        feedback_dataset_id=ds.dataset_id,
        inject=inj,
        summary="golden failure",
        session_id="h1",
    )
    assert case.case_id
    h1 = compute_feedback_dataset_hash(
        strategy_code=STRATEGY_CODE,
        feedback_type="PERFORMANCE_FEEDBACK",
        schema_version=ds.schema_version,
        filter_spec=ds.filter_spec,
        window_start=ds.window_start,
        window_end=ds.window_end,
        processor_id=ds.processor_id,
        processor_version=ds.processor_version,
        rows=ds.rows,
    )
    assert h1 == ds.dataset_hash
    h2 = compute_feedback_dataset_hash(
        strategy_code=STRATEGY_CODE,
        feedback_type="PERFORMANCE_FEEDBACK",
        schema_version=ds.schema_version,
        filter_spec={**ds.filter_spec, "extra": 1},
        window_start=ds.window_start,
        window_end=ds.window_end,
        processor_id=ds.processor_id,
        processor_version=ds.processor_version,
        rows=ds.rows,
    )
    assert h2 != ds.dataset_hash

    from app.services.production_research_feedback.protocol import ResearchFeedbackQuery

    rows = dq.production_feedback(
        ResearchFeedbackQuery(strategy_code=STRATEGY_CODE, reality_kind="ACTUAL")
    )
    assert any(r.record_kind == "DATASET" for r in rows)
    assert any(r.record_kind == "SNAPSHOT" for r in rows)
    assert snap.pnl_summary.pnl_total == 1000.0


def test_snapshot_immutable_and_correction(tmp_path):
    svc, _reg, _dq = make_feedback_env(tmp_path / "snap")
    inj = golden_production_feedback_inject()
    first = svc.build_reality_snapshot(STRATEGY_CODE, inject=inj, session_id="h2")
    bad = {
        "production_feedback": {
            **inj["production_feedback"],
            "metrics": {"return_total": 0.99},
        }
    }
    with pytest.raises(ProductionResearchFeedbackError):
        svc.build_reality_snapshot(STRATEGY_CODE, inject=bad, session_id="h2")
    v2 = svc.build_reality_snapshot(
        STRATEGY_CODE,
        inject=bad,
        correction_of=first.snapshot_id,
        session_id="h2c",
    )
    assert v2.snapshot_version == 2
    assert v2.supersedes_snapshot_id == first.snapshot_id


def test_quality_gate_rejects_bad_inject(tmp_path):
    svc, _reg, _dq = make_feedback_env(tmp_path / "gate")
    with pytest.raises(ProductionResearchFeedbackError):
        svc.build_dataset(
            STRATEGY_CODE,
            "PERFORMANCE_FEEDBACK",
            "2025-05-01",
            "2025-06-01",
            inject=golden_bad_pit_lineage_inject(),
        )


def test_hypothesis_experiment_lineage(tmp_path):
    svc, reg, _dq = make_feedback_env(tmp_path / "hyp")
    inj = golden_production_feedback_inject()
    ds = svc.build_dataset(
        STRATEGY_CODE,
        "DRIFT_FEEDBACK",
        "2025-05-01",
        "2025-06-01",
        inject=inj,
    )
    case = svc.record_failure_case(STRATEGY_CODE, feedback_dataset_id=ds.dataset_id, inject=inj)
    hyp = svc.create_hypothesis(
        STRATEGY_CODE,
        "drift root cause",
        failure_case_ids=[case.case_id],
        feedback_dataset_id=ds.dataset_id,
    )
    link = svc.link_experiment(
        "exp_golden_1",
        strategy_code=STRATEGY_CODE,
        feedback_dataset_id=ds.dataset_id,
        failure_case_ids=[case.case_id],
        incident_ids=[case.incident_id],
        hypothesis_id=hyp.hypothesis_id,
    )
    stored = reg.get_feedback_experiment_link(link.link_id)
    assert stored.parent_feedback_dataset_id == ds.dataset_id
    assert case.case_id in stored.parent_failure_case_ids_json
    assert case.incident_id in stored.parent_incident_ids_json


def test_counterfactual_isolated_from_actual(tmp_path):
    svc, reg, _dq = make_feedback_env(tmp_path / "cf")
    inj = golden_production_feedback_inject()
    snap = svc.build_reality_snapshot(STRATEGY_CODE, inject=inj)
    cf = svc.build_counterfactual(snap.snapshot_id, {"name": "shock", "pnl_shock": -200.0})
    assert cf.reality_kind == "COUNTERFACTUAL"
    actual = svc.get_snapshot(snap.snapshot_id)
    assert actual.pnl_summary.pnl_total == 1000.0
    cf_rows = reg.list_production_reality_snapshots(STRATEGY_CODE, reality_kind="COUNTERFACTUAL")
    assert cf_rows
    assert all(float(r.pnl_total or 0.0) == 0.0 for r in cf_rows)


def test_no_forbidden_tokens_in_package():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "production_research_feedback"
    )
    forbidden = ("train_model", "mutate_version", "promote", "submit_order")
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text


def test_no_trading_db_imports_in_package():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "production_research_feedback"
    )
    banned = ("oms", "trading_db", "broker_order")
    for py in root.rglob("*.py"):
        src = py.read_text(encoding="utf-8").lower()
        for token in banned:
            assert token not in src
