"""Phase 9F-3 — TrainingJob / TrainingRun orchestration。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.model_platform.runner import ModelPlatformError
from model_platform_golden.golden import (
    GOLDEN_DATASET_HASH,
    formal_inject,
    golden_job_spec,
    golden_model_spec,
    make_model_platform_env,
)


def test_happy_path_job_to_version(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "ok")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(model_id=model.model_id, idempotency_key="k1")
    )
    assert job.status == "OPEN"
    assert len(job.run_ids) == 1
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    assert run.status == "SUCCEEDED"
    assert run.model_version_id
    assert run.logs_uri and run.metrics_uri
    assert run.metrics.get("best_iteration") == 42
    ver = svc.get_version(run.model_version_id)
    assert ver.lifecycle == "TRAINED"
    assert ver.dataset_hash == GOLDEN_DATASET_HASH
    job2 = svc.get_job(job.job_id)
    assert job2.status == "CLOSED"


def test_prepare_missing_dataset(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "miss")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            dataset_hash="",
            idempotency_key="miss",
            force_new=True,
        )
    )
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    assert run.status == "FAILED"
    assert run.failure_class == "DATA_MISSING"
    assert not run.model_version_id
    assert svc.list_versions(model.model_id) == []


def test_running_inject_fail(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "runfail")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(model_id=model.model_id, force_new=True, idempotency_key="rf")
    )
    run = svc.execute_training_run(
        job.run_ids[0],
        inject=formal_inject(simulate_fail_at="RUNNING"),
    )
    assert run.status == "FAILED"
    assert run.failure_class == "MODEL_ERROR"
    assert svc.list_versions(model.model_id) == []


def test_cancel_running(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "cancel")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(model_id=model.model_id, force_new=True, idempotency_key="c1")
    )
    rid = job.run_ids[0]
    svc.update_training_run_status(rid, "PREPARING")
    svc.update_training_run_status(rid, "RUNNING")
    cancelled = svc.cancel_training_run(rid)
    assert cancelled.status == "CANCELLED"


def test_retry_after_fail(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "retry")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(model_id=model.model_id, force_new=True, idempotency_key="r1")
    )
    failed = svc.execute_training_run(
        job.run_ids[0],
        inject=formal_inject(simulate_fail_at="PREPARING"),
    )
    assert failed.status == "FAILED"
    child = svc.retry_training_run(failed.training_run_id)
    assert child.parent_training_run_id == failed.training_run_id
    assert child.retry_index == 1
    assert child.job_id == job.job_id
    ok = svc.execute_training_run(child.training_run_id, inject=formal_inject())
    assert ok.status == "SUCCEEDED"
    assert ok.model_version_id


def test_terminal_immutable(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "term")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(model_id=model.model_id, force_new=True, idempotency_key="t1")
    )
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    with pytest.raises(ModelPlatformError):
        svc.update_training_run_status(run.training_run_id, "RUNNING")
    with pytest.raises(ModelPlatformError):
        svc.execute_training_run(run.training_run_id, inject=formal_inject())


def test_no_qlib_or_trainer_imports():
    pkg = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "model_platform"
    )
    for py in pkg.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "from app.services.research_data.model_training" not in text
        assert "import qlib" not in text
        assert "from qlib" not in text
        assert "ModelTrainer(" not in text
