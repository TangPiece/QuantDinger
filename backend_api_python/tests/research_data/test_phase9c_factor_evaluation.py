"""Phase 9C — Factor Evaluation Platform。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.evaluation_platform.protocol import ENGINE_VERSION
from app.services.research_data.evaluation_platform.runner import (
    FactorEvaluationPlatformError,
    FactorEvaluationPlatformService,
)
from evaluation_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    GOLDEN_FACTOR_REF,
    GOLDEN_POLICY_ALT_ID,
    GOLDEN_POLICY_ID,
    evaluation_inject,
    make_evaluation_platform_env,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_evaluation_platform@1"


def test_gate_blocked_no_ic_pointers(tmp_path):
    svc, ds, _reg, days, window = make_evaluation_platform_env(tmp_path / "gate")
    run = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=evaluation_inject(gate_blocked=True, days=days),
    )
    assert run.status == "BLOCKED"
    assert run.gate_verdict == "BLOCKED"
    assert not run.evaluation_hash
    assert not run.metric_hash
    assert not run.group_evaluation_hash
    assert not run.stability_hash
    with pytest.raises(FactorEvaluationPlatformError):
        svc.get_quality_score(run.evaluation_id)


def test_success_binds_lineage_and_pointers(tmp_path):
    svc, ds, _reg, days, window = make_evaluation_platform_env(tmp_path / "ok")
    run = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=evaluation_inject(days=days),
    )
    assert run.status == "SUCCESS"
    assert len(run.factor_hash) == 64
    assert run.dataset_hash == ds.get(GOLDEN_DATASET_REF).dataset_hash
    assert run.policy_id == GOLDEN_POLICY_ID
    assert run.evaluation_hash
    assert run.metric_hash
    assert run.group_evaluation_hash
    assert run.stability_hash
    score = svc.get_quality_score(run.evaluation_id)
    assert score.total_score >= 0.0
    assert score.raw_metrics.get("ic_by_horizon")
    lin = svc.get_lineage(run.evaluation_id)
    assert lin.kind == "EVALUATION_RUN"
    kinds = {c.kind for c in lin.children}
    assert "FACTOR" in kinds and "DATASET" in kinds and "EVALUATION_POLICY" in kinds


def test_idempotent_same_inputs(tmp_path):
    svc, _ds, _reg, days, window = make_evaluation_platform_env(tmp_path / "idem")
    inj = evaluation_inject(days=days)
    r1 = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=inj,
    )
    r2 = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=inj,
    )
    assert r1.evaluation_id == r2.evaluation_id
    assert r1.run_content_hash == r2.run_content_hash


def test_policy_change_new_run(tmp_path):
    svc, _ds, _reg, days, window = make_evaluation_platform_env(tmp_path / "pol")
    inj = evaluation_inject(days=days)
    r1 = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=inj,
    )
    r2 = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ALT_ID,
        window=window,
        inject=inj,
    )
    assert r1.run_content_hash != r2.run_content_hash
    assert r1.evaluation_id != r2.evaluation_id


def test_list_runs_and_get_by_hash(tmp_path):
    svc, _ds, _reg, days, window = make_evaluation_platform_env(tmp_path / "list")
    run = svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=evaluation_inject(days=days),
    )
    assert svc.get_by_hash(run.run_content_hash) is not None
    listed = svc.list_runs(factor_hash=run.factor_hash)
    assert any(x.evaluation_id == run.evaluation_id for x in listed)


def test_no_forbidden_apis():
    forbidden = (
        "mine_factors",
        "promote",
        "capacity_curve",
        "train_model",
        "mine",
    )
    for name in forbidden:
        assert not hasattr(FactorEvaluationPlatformService, name)


def test_package_no_trading_db_imports():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "evaluation_platform"
    )
    forbidden = ("trading_db", "submit_order", "production_oms", "psycopg")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for tok in forbidden:
            assert tok not in text, f"{path.name} contains {tok}"
