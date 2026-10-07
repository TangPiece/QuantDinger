"""Phase 9F-6：Model Evaluation。"""

from __future__ import annotations

from pathlib import Path

from app.services.research_data.model_evaluation import (
    ENGINE_VERSION,
    ModelEvaluationRequest,
    ModelEvaluationService,
)
from app.services.research_data.model_evaluation.protocol import ModelEvaluationInject
from app.services.research_data.model_platform.runner import ModelPlatformService
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)


def _panel(*, n_dates: int = 5, n_inst: int = 8, seed: float = 0.05):
    rows = []
    for d in range(n_dates):
        date = f"2024-01-{d+1:02d}"
        for i in range(n_inst):
            # prediction correlated with label
            label = float(i) + d * 0.01
            pred = label * seed + i * 0.1
            rows.append(
                {
                    "date": date,
                    "instrument": f"CNStock:{i:06d}",
                    "prediction": pred,
                    "label": label,
                }
            )
    return rows


def test_engine_version():
    assert ENGINE_VERSION == "qd_model_evaluation@1"


def test_no_evaluate_model_on_platform():
    assert not hasattr(ModelPlatformService, "evaluate_model")


def test_success_path_inject_predictions(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "plat")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    svc = ModelEvaluationService(tmp_path / "eval", model_platform=plat)
    req = ModelEvaluationRequest(
        model_version_id=ver.model_version_id,
        evaluation_dataset_hash="e" * 64,
        dataset_hash="d" * 64,
        feature_set_hash="f" * 64,
        label_hash="b" * 64,
        snapshot_id="snap_eval",
        evaluation_start="2024-01-01",
        evaluation_end="2024-01-31",
    )
    run = svc.run_evaluation(
        req,
        inject=ModelEvaluationInject(
            predictions=_panel(),
            known_hashes={
                "evaluation_dataset_hash": "e" * 64,
                "feature_set_hash": "f" * 64,
                "label_hash": "b" * 64,
                "snapshot_id": "snap_eval",
            },
        ),
    )
    assert run.status == "SUCCEEDED"
    assert run.result is not None
    assert run.result.quality_status == "PASS"
    assert run.result.raw_metrics["predictive"]["mean_ic"] is not None
    assert run.result.raw_metrics["predictive"]["mean_rank_ic"] is not None
    art = svc.get_artifact_dir(run.evaluation_run_id)
    assert (art / "metrics.json").is_file()
    assert (art / "manifest.json").is_file()
    assert (art / "predictions.parquet").is_file() or (art / "predictions.json").is_file()


def test_two_windows_two_runs(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "plat2")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    svc = ModelEvaluationService(tmp_path / "eval2", model_platform=plat)
    base = dict(
        model_version_id=ver.model_version_id,
        evaluation_dataset_hash="e" * 64,
        feature_set_hash="f" * 64,
        label_hash="b" * 64,
        snapshot_id="snap",
    )
    inj = ModelEvaluationInject(predictions=_panel())
    r1 = svc.run_evaluation(
        ModelEvaluationRequest(
            **base, evaluation_start="2024-01-01", evaluation_end="2024-03-31"
        ),
        inject=inj,
    )
    r2 = svc.run_evaluation(
        ModelEvaluationRequest(
            **base, evaluation_start="2024-04-01", evaluation_end="2024-06-30"
        ),
        inject=inj,
    )
    assert r1.evaluation_run_id != r2.evaluation_run_id
    assert r1.run_content_hash != r2.run_content_hash
    listed = svc.list_runs_for_version(ver.model_version_id)
    assert len(listed) >= 2


def test_idempotent_same_hash(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "plat3")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    svc = ModelEvaluationService(tmp_path / "eval3", model_platform=plat)
    req = ModelEvaluationRequest(
        model_version_id=ver.model_version_id,
        evaluation_dataset_hash="e" * 64,
        feature_set_hash="f" * 64,
        label_hash="b" * 64,
        evaluation_start="2024-01-01",
        evaluation_end="2024-01-31",
    )
    inj = ModelEvaluationInject(predictions=_panel())
    a = svc.run_evaluation(req, inject=inj)
    b = svc.run_evaluation(req, inject=inj)
    assert a.evaluation_run_id == b.evaluation_run_id


def test_pit_gate_blocked(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "plat4")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    svc = ModelEvaluationService(tmp_path / "eval4", model_platform=plat)
    run = svc.run_evaluation(
        ModelEvaluationRequest(
            model_version_id=ver.model_version_id,
            evaluation_dataset_hash="e" * 64,
            feature_set_hash="f" * 64,
            label_hash="b" * 64,
            evaluation_start="2024-01-01",
            evaluation_end="2024-01-31",
        ),
        inject=ModelEvaluationInject(predictions=_panel(), force_pit_fail=True),
    )
    assert run.status == "BLOCKED"
    assert run.result is not None
    assert run.result.overall_status == "BLOCKED"
    assert "pit_violation" in run.gate_reasons


def test_missing_eval_hash_blocked(tmp_path: Path):
    svc = ModelEvaluationService(tmp_path / "eval5")
    run = svc.run_evaluation(
        ModelEvaluationRequest(
            model_version_id="mver_x",
            evaluation_start="2024-01-01",
            evaluation_end="2024-01-31",
        ),
        inject=ModelEvaluationInject(
            predictions=_panel(),
            skip_artifact_check=True,
        ),
    )
    assert run.status == "BLOCKED"
    assert any("evaluation_dataset_hash" in r for r in run.gate_reasons)
