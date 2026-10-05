"""Phase 2F：Experiment 编排 / manifest / 复现 / MLflow 绑定。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.experiment import (
    ExperimentManifestStore,
    ExperimentRunner,
    ExperimentSpec,
    is_reproducible,
)
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.model_training import (
    ModelArtifactStore,
    ModelTrainSpec,
    builtin_lgb_baseline_model,
)
from app.services.research_data.model_training.adapter import lightgbm_runtime_available
from app.services.research_data.qlib_adapter import (
    QlibAdapter,
    ResearchDatasetSpec,
    SegmentRange,
    SegmentSpec,
    VersionResolver,
    builtin_qd_standard_processor,
)
from app.services.research_data.signal import EqualWeightPortfolio, SignalRunSpec, TopKStrategy
from app.services.research_data.signal.artifact_store import SignalArtifactStore


def _segments() -> SegmentSpec:
    return SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )


def _require_lgb() -> None:
    pytest.importorskip("qlib")
    if not lightgbm_runtime_available():
        pytest.skip("lightgbm unavailable (install libomp on macOS)")


def _upsert_dataset(
    golden_qlib_env,
    *,
    version: str,
    processor: str | None = "qd_standard@1",
    price_policy: PricePolicy | None = None,
) -> str:
    registry = golden_qlib_env["registry"]
    handle = golden_qlib_env["query"].dataset(golden_qlib_env["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version=version,
        name=f"phase2f {version}",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=price_policy or base.price_policy,
        processor=processor,
        pit=True,
    )
    registry.upsert_dataset(definition, status="validated")
    return f"{GOLDEN_DATASET_CODE}@{version}"


def _make_runner(golden_qlib_env, tmp_path: Path) -> tuple[ExperimentRunner, ExperimentManifestStore]:
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_qd_standard_processor())
    registry.upsert_model(builtin_lgb_baseline_model())
    adapter = QlibAdapter(
        golden_qlib_env["query"],
        materializer=golden_qlib_env["materializer"],
        registry=registry,
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    model_store = ModelArtifactStore(root=tmp_path / "model_art")
    signal_store = SignalArtifactStore(root=tmp_path / "signal_art")
    manifest_store = ExperimentManifestStore(root=tmp_path / "exp_art")
    from app.services.research_data.model_training import ModelTrainer
    from app.services.research_data.signal import SignalPipeline

    trainer = ModelTrainer(adapter, registry, artifact_store=model_store)
    signals = SignalPipeline(registry, artifact_store=signal_store)
    runner = ExperimentRunner(
        adapter,
        registry,
        model_trainer=trainer,
        signal_pipeline=signals,
        manifest_store=manifest_store,
    )
    return runner, manifest_store


def _base_spec(
    dataset_ref: str,
    *,
    seed: int = 42,
    num_leaves: int | None = None,
    model_code: str | None = None,
) -> ExperimentSpec:
    model = builtin_lgb_baseline_model()
    override: dict = {}
    if num_leaves is not None:
        override["num_leaves"] = num_leaves
        # 不同超参用独立 model code，避免 Local Registry 按 code 整包不可变冲突
        code = model_code or f"lgb_leaves{num_leaves}"
        model = model.model_copy(
            update={
                "code": code,
                "name": f"LightGBM leaves={num_leaves}",
                "config": {**model.config, "num_leaves": num_leaves},
            }
        )
    elif model_code:
        model = model.model_copy(update={"code": model_code, "name": model_code})
    return ExperimentSpec(
        name="phase2f_test",
        train=ModelTrainSpec(
            dataset_spec=ResearchDatasetSpec(
                dataset_ref=dataset_ref, segments=_segments()
            ),
            model=model,
            seed=seed,
            config_override=override,
        ),
        signal=SignalRunSpec(
            strategy=TopKStrategy(k=2),
            portfolio=EqualWeightPortfolio(),
        ),
        seed=seed,
    )


def test_experiment_create_and_manifest(golden_qlib_env, tmp_path, monkeypatch):
    _require_lgb()
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    runner, store = _make_runner(golden_qlib_env, tmp_path)
    dataset_ref = _upsert_dataset(golden_qlib_env, version="v1_2f")
    result = runner.run(_base_spec(dataset_ref))

    assert result.experiment_id.startswith("exp_")
    assert result.model_artifact_id
    assert result.signal_artifact_id
    assert result.strategy_version == "topk@1"
    assert "valid_mse" in result.metrics
    assert "valid_rank_ic" in result.metrics
    assert "long_count" in result.metrics

    # Registry
    exp = golden_qlib_env["registry"].get_experiment(result.experiment_id)
    assert exp.dataset_hash == result.dataset_hash
    assert exp.manifest_uri == result.manifest_uri

    # Manifest 可仅凭 experiment_id 恢复
    man = store.read(result.experiment_id)
    assert man.dataset_hash == result.dataset_hash
    assert man.model_artifact_id == result.model_artifact_id
    assert man.signal_artifact_id == result.signal_artifact_id

    # dataset_hash 与 VersionResolver 一致
    bundle = VersionResolver(
        golden_qlib_env["query"], golden_qlib_env["registry"]
    ).resolve(dataset_ref)
    assert man.dataset_hash == bundle.dataset_hash

    # Artifact 链
    model_art = golden_qlib_env["registry"].get_artifact(result.model_artifact_id)
    signal_art = golden_qlib_env["registry"].get_artifact(result.signal_artifact_id)
    assert model_art.checksum
    assert signal_art.checksum
    assert Path(model_art.storage_uri).exists()
    assert Path(signal_art.storage_uri).exists()


def test_mlflow_run_bidirectional(golden_qlib_env, tmp_path, monkeypatch):
    _require_lgb()
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    mlflow = pytest.importorskip("mlflow")
    runner, _ = _make_runner(golden_qlib_env, tmp_path)
    dataset_ref = _upsert_dataset(golden_qlib_env, version="v1_2f_mlflow")
    result = runner.run(_base_spec(dataset_ref))
    assert result.mlflow_run_id
    exp = golden_qlib_env["registry"].get_experiment(result.experiment_id)
    assert exp.mlflow_run_id == result.mlflow_run_id

    mlflow.set_tracking_uri(f"file:{tmp_path / 'mlruns'}")
    run = mlflow.get_run(result.mlflow_run_id)
    assert run.data.tags.get("qd.experiment_id") == result.experiment_id
    assert run.data.params.get("dataset_hash") == result.dataset_hash


def test_reproducible_same_spec(golden_qlib_env, tmp_path, monkeypatch):
    _require_lgb()
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    runner, _ = _make_runner(golden_qlib_env, tmp_path)
    dataset_ref = _upsert_dataset(golden_qlib_env, version="v1_2f_repro")
    spec = _base_spec(dataset_ref)
    a = runner.run(spec)
    b = runner.run(spec)
    assert a.experiment_id == b.experiment_id
    assert is_reproducible(a, b)


def test_price_policy_changes_dataset_hash_and_experiment_id(
    golden_qlib_env, tmp_path, monkeypatch
):
    _require_lgb()
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    runner, _ = _make_runner(golden_qlib_env, tmp_path)
    ref_a = _upsert_dataset(golden_qlib_env, version="v1_2f_pol_a")
    ref_b = _upsert_dataset(
        golden_qlib_env,
        version="v1_2f_pol_b",
        price_policy=PricePolicy(adjustment="none", return_type="total"),
    )
    a = runner.run(_base_spec(ref_a))
    b = runner.run(_base_spec(ref_b))
    assert a.dataset_hash != b.dataset_hash
    assert a.experiment_id != b.experiment_id


def test_model_config_change_keeps_dataset_hash(
    golden_qlib_env, tmp_path, monkeypatch
):
    _require_lgb()
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    runner, _ = _make_runner(golden_qlib_env, tmp_path)
    dataset_ref = _upsert_dataset(golden_qlib_env, version="v1_2f_leaves")
    a = runner.run(_base_spec(dataset_ref, num_leaves=8))
    b = runner.run(_base_spec(dataset_ref, num_leaves=16))
    assert a.dataset_hash == b.dataset_hash
    assert a.repro_fingerprint != b.repro_fingerprint
    assert a.experiment_id != b.experiment_id
