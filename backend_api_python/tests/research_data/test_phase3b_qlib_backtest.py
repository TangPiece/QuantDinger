"""Phase 3B：Qlib Research Backtest 六项验收。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.research_data.backtest import (
    BacktestRequest,
    compute_request_fingerprint,
    research_qlib_relaxed,
)
from app.services.research_data.contracts import DatasetDefinition
from app.services.research_data.experiment import (
    ExperimentManifestStore,
    ExperimentRunner,
    ExperimentSpec,
)
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.model_training import (
    ModelArtifactStore,
    ModelTrainSpec,
    ModelTrainer,
    builtin_lgb_baseline_model,
)
from app.services.research_data.model_training.adapter import lightgbm_runtime_available
from app.services.research_data.qlib_adapter import (
    QlibAdapter,
    ResearchDatasetSpec,
    SegmentRange,
    SegmentSpec,
    builtin_qd_standard_processor,
)
from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.signal import EqualWeightPortfolio, SignalPipeline, SignalRunSpec, TopKStrategy
from app.services.research_data.signal.artifact_store import SignalArtifactStore


def _require_lgb_qlib() -> None:
    pytest.importorskip("qlib")
    if not lightgbm_runtime_available():
        pytest.skip("lightgbm unavailable (install libomp on macOS)")


def _segments() -> SegmentSpec:
    return SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )


def _upsert_dataset(golden_qlib_env, *, version: str) -> str:
    registry = golden_qlib_env["registry"]
    handle = golden_qlib_env["query"].dataset(golden_qlib_env["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version=version,
        name=f"phase3b {version}",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=base.price_policy,
        processor="qd_standard@1",
        pit=True,
    )
    registry.upsert_dataset(definition, status="validated")
    return f"{GOLDEN_DATASET_CODE}@{version}"


def _make_runner(golden_qlib_env, tmp_path: Path) -> tuple[ExperimentRunner, QlibAdapter]:
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
    trainer = ModelTrainer(
        adapter, registry, artifact_store=ModelArtifactStore(root=tmp_path / "model_art")
    )
    signals = SignalPipeline(
        registry, artifact_store=SignalArtifactStore(root=tmp_path / "signal_art")
    )
    runner = ExperimentRunner(
        adapter,
        registry,
        model_trainer=trainer,
        signal_pipeline=signals,
        manifest_store=ExperimentManifestStore(root=tmp_path / "exp_art"),
    )
    return runner, adapter


def _run_experiment(golden_qlib_env, tmp_path: Path, *, version: str):
    """跑通 LGB + TopK，返回 (exp_result, adapter, dataset_ref)。"""
    _require_lgb_qlib()
    dataset_ref = _upsert_dataset(golden_qlib_env, version=version)
    runner, adapter = _make_runner(golden_qlib_env, tmp_path)
    spec = ExperimentSpec(
        name="phase3b_test",
        train=ModelTrainSpec(
            dataset_spec=ResearchDatasetSpec(dataset_ref=dataset_ref, segments=_segments()),
            model=builtin_lgb_baseline_model(),
            seed=42,
        ),
        signal=SignalRunSpec(
            strategy=TopKStrategy(k=2),
            portfolio=EqualWeightPortfolio(),
        ),
        seed=42,
    )
    return runner.run(spec), adapter, dataset_ref


def _build_request(golden_qlib_env, exp_result, *, dataset_ref: str) -> BacktestRequest:
    registry = golden_qlib_env["registry"]
    experiment = registry.get_experiment(exp_result.experiment_id)
    exec_p, price_p, cost_p, rules = research_qlib_relaxed()
    return BacktestRequest.from_experiment(
        experiment,
        start_date="2024-05-01",
        end_date="2024-06-30",
        initial_capital=1_000_000.0,
        engine="qlib",
        execution_policy=exec_p,
        market_price_policy=price_p,
        cost_policy=cost_p,
        trading_rule=rules,
    ).model_copy(
        update={
            "dataset_ref": dataset_ref,
            "benchmark": None,
            "target_positions_artifact_id": exp_result.signal_artifact_id,
            "signal_run_id": exp_result.signal_run_id
            if hasattr(exp_result, "signal_run_id")
            else experiment.signal_run_id,
        }
    )


def _engine(adapter, registry, tmp_path: Path):
    from app.services.research_data.backtest_qlib import (
        BacktestArtifactStore,
        QlibResearchBacktestEngine,
    )

    return QlibResearchBacktestEngine(
        adapter,
        registry,
        artifact_store=BacktestArtifactStore(root=tmp_path / "bt_art"),
    )


def test_minimal_backtest_equity_or_metrics(golden_qlib_env, tmp_path, monkeypatch):
    """1. 最小回测：非空 equity 或 metrics。"""
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    exp, adapter, dataset_ref = _run_experiment(
        golden_qlib_env, tmp_path, version="v1_3b_min"
    )
    req = _build_request(golden_qlib_env, exp, dataset_ref=dataset_ref)
    eng = _engine(adapter, golden_qlib_env["registry"], tmp_path)
    result = eng.run(req)
    assert result.engine == "qlib"
    has_equity = len(result.equity_curve) > 0
    has_metrics = (
        result.metrics.total_return is not None or result.metrics.sharpe is not None
    )
    assert has_equity or has_metrics
    assert result.artifact_uris


def test_dataset_hash_consistent(golden_qlib_env, tmp_path, monkeypatch):
    """2. dataset_hash 与 Experiment / Request 一致。"""
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    exp, adapter, dataset_ref = _run_experiment(
        golden_qlib_env, tmp_path, version="v1_3b_hash"
    )
    req = _build_request(golden_qlib_env, exp, dataset_ref=dataset_ref)
    experiment = golden_qlib_env["registry"].get_experiment(exp.experiment_id)
    assert req.dataset_hash == experiment.dataset_hash == exp.dataset_hash
    result = _engine(adapter, golden_qlib_env["registry"], tmp_path).run(req)
    assert result.dataset_hash == req.dataset_hash


def test_experiment_id_traceable(golden_qlib_env, tmp_path, monkeypatch):
    """3. experiment_id 可追溯 Registry（dataset/model/signal refs）。"""
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    exp, adapter, dataset_ref = _run_experiment(
        golden_qlib_env, tmp_path, version="v1_3b_trace"
    )
    req = _build_request(golden_qlib_env, exp, dataset_ref=dataset_ref)
    result = _engine(adapter, golden_qlib_env["registry"], tmp_path).run(req)
    experiment = golden_qlib_env["registry"].get_experiment(result.experiment_id)
    assert experiment.dataset_ref
    assert experiment.model_artifact_id
    assert experiment.signal_artifact_id
    assert result.experiment_id == exp.experiment_id


def test_double_run_fingerprint_and_equity(golden_qlib_env, tmp_path, monkeypatch):
    """4. 双跑同 fingerprint；equity 末值容差内一致。"""
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    exp, adapter, dataset_ref = _run_experiment(
        golden_qlib_env, tmp_path, version="v1_3b_repro"
    )
    req = _build_request(golden_qlib_env, exp, dataset_ref=dataset_ref)
    eng = _engine(adapter, golden_qlib_env["registry"], tmp_path)
    a = eng.run(req)
    b = eng.run(req)
    assert a.request_fingerprint == b.request_fingerprint == compute_request_fingerprint(req)
    if a.equity_curve and b.equity_curve:
        assert abs(a.equity_curve[-1].equity - b.equity_curve[-1].equity) < 1e-4
    else:
        assert a.metrics.total_return == b.metrics.total_return


def test_weight_alignment_sample_day(golden_qlib_env, tmp_path, monkeypatch):
    """5. 抽样日 TargetPosition 与 loader Series 对齐。"""
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    from app.services.research_data.backtest_qlib import load_target_weight_series, weights_for_date

    exp, adapter, dataset_ref = _run_experiment(
        golden_qlib_env, tmp_path, version="v1_3b_w"
    )
    art = golden_qlib_env["registry"].get_artifact(exp.signal_artifact_id)
    series = load_target_weight_series(art)
    # 取第一个有权重的交易日
    day = series.index.get_level_values("datetime")[0]
    mapped = weights_for_date(series, day)
    assert mapped
    import pyarrow.parquet as pq

    df = pq.read_table(Path(art.storage_uri) / "target_positions.parquet").to_pandas()
    day_str = day.strftime("%Y-%m-%d")
    day_rows = df[df["trading_date"].astype(str).str[:10] == day_str]
    assert not day_rows.empty
    for _, row in day_rows.iterrows():
        qid = to_qlib_instrument(str(row["instrument_key"])).lower()
        assert qid in mapped
        assert abs(mapped[qid] - float(row["target_weight"])) < 1e-9
    # 跑一次回测确保策略可消费同一 Series
    req = _build_request(golden_qlib_env, exp, dataset_ref=dataset_ref)
    result = _engine(adapter, golden_qlib_env["registry"], tmp_path).run(req)
    assert result.result_id


def test_result_completeness(golden_qlib_env, tmp_path, monkeypatch):
    """6. result_id / equity_curve / metrics / artifact_uris 完整。"""
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{tmp_path / 'mlruns'}")
    exp, adapter, dataset_ref = _run_experiment(
        golden_qlib_env, tmp_path, version="v1_3b_full"
    )
    req = _build_request(golden_qlib_env, exp, dataset_ref=dataset_ref)
    result = _engine(adapter, golden_qlib_env["registry"], tmp_path).run(req)
    assert result.result_id
    assert result.equity_curve is not None
    assert result.metrics is not None
    assert result.artifact_uris
    assert "result" in result.artifact_uris
    assert result.engine_version
    assert result.request_fingerprint == compute_request_fingerprint(req)
