"""Phase 9F-4：Model Adapter Contract + Qlib 分发（stub 路径始终可跑）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.model_adapters import (
    ADAPTER_ENGINE_VERSION,
    ModelAdapterError,
    ModelArtifactCandidate,
    PredictionRequest,
    TrainingContext,
    TrainingSegments,
    default_adapter_registry,
    map_training_config_to_lgb,
)
from app.services.research_data.model_platform.executor import resolve_executor_kind
from app.services.research_data.model_platform.protocol import ENGINE_VERSION
from app.services.research_data.model_platform.runner import ModelPlatformError
from model_platform_golden.golden import (
    formal_inject,
    golden_job_spec,
    golden_model_spec,
    make_model_platform_env,
)


def test_adapter_registry_lightgbm():
    reg = default_adapter_registry()
    assert "LIGHTGBM" in reg.keys()
    assert ADAPTER_ENGINE_VERSION.startswith("qd_model_adapter")


def test_config_map_deterministic():
    a = map_training_config_to_lgb(
        {"algorithm": "lightgbm", "objective": "regression", "parameters": {"num_leaves": 16}},
        hyperparameters={"num_boost_round": 10},
        seed=7,
    )
    b = map_training_config_to_lgb(
        {"algorithm": "lightgbm", "objective": "regression", "parameters": {"num_leaves": 16}},
        hyperparameters={"num_boost_round": 10},
        seed=7,
    )
    assert a == b
    assert a["seed"] == 7
    assert a["num_leaves"] == 16
    assert a["num_boost_round"] == 10


def test_executor_kind_stub_vs_qlib(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "kind")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            resource_config={"executor": "stub"},
            force_new=True,
            idempotency_key="k-stub",
        )
    )
    run = svc.get_training_run(job.run_ids[0])
    assert resolve_executor_kind(run) == "stub"

    job2 = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            requested_version="2.0.0",
            resource_config={"executor": "qlib"},
            dataset_ref="demo@v1",
            force_new=True,
            idempotency_key="k-qlib",
        )
    )
    run2 = svc.get_training_run(job2.run_ids[0])
    assert resolve_executor_kind(run2) == "qlib"
    assert run2.dataset_ref == "demo@v1"


def test_qlib_prepare_requires_dataset_ref(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "noref")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            resource_config={"executor": "qlib"},
            dataset_ref="",
            force_new=True,
            idempotency_key="k-noref",
        )
    )
    # 无 qlib deps → fail at prepare/resource；有 dataset_ref 缺失也失败
    run = svc.execute_training_run(
        job.run_ids[0],
        inject=formal_inject(skip_dataset_ref_check=True),
    )
    assert run.status == "FAILED"
    assert run.failure_class in ("CONFIG_ERROR", "RESOURCE_ERROR", "DATA_MISSING")
    assert not run.model_version_id


def test_stub_path_still_succeeds(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "stubok")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            resource_config={"executor": "local"},
            force_new=True,
            idempotency_key="k-local",
        )
    )
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    assert run.status == "SUCCEEDED"
    assert run.model_version_id
    ver = svc.get_version(run.model_version_id)
    assert ver.lifecycle == "TRAINED"


def test_model_platform_no_direct_qlib_import():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "model_platform"
    )
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "from app.services.research_data.model_training" not in text
        assert "import qlib" not in text
        assert "from qlib" not in text


def test_training_context_validate_config():
    from app.services.research_data.model_adapters import QlibModelAdapter

    adp = QlibModelAdapter()  # no deps — validate_config only
    with pytest.raises(ModelAdapterError):
        adp.validate_config(
            TrainingContext(training_run_id="x", dataset_ref="", segments=TrainingSegments())
        )
    with pytest.raises(ModelAdapterError):
        adp.validate_config(
            TrainingContext(
                training_run_id="x",
                dataset_ref="a@1",
                segments=TrainingSegments(train_start="2024-01-01", train_end="2024-01-31"),
            )
        )


def test_engine_versions():
    assert ENGINE_VERSION == "qd_model_platform@1"
    assert ADAPTER_ENGINE_VERSION == "qd_model_adapter@1"


def test_artifact_candidate_shape():
    c = ModelArtifactCandidate(
        artifact_uri="/tmp/model.bin",
        checksum="a" * 64,
        file_size=10,
        metrics={"valid_mse": 0.1},
    )
    assert c.framework == "LIGHTGBM"
    assert c.adapter_version == ADAPTER_ENGINE_VERSION
