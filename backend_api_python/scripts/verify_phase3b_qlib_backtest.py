#!/usr/bin/env python3
"""Phase 3B 验收：Qlib Research Backtest 端到端。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_phase3b_qlib_backtest.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def main() -> int:
    try:
        import qlib  # noqa: F401
    except ImportError:
        print(json.dumps({"ok": False, "error": "pyqlib not installed"}, ensure_ascii=False))
        return 2

    from app.services.research_data.model_training.adapter import lightgbm_runtime_available

    if not lightgbm_runtime_available():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "lightgbm unavailable (macOS: brew install libomp)",
                },
                ensure_ascii=False,
            )
        )
        return 2

    from app.services.research_data.backtest import (
        compute_request_fingerprint,
        research_qlib_relaxed,
    )
    from app.services.research_data.backtest.request import BacktestRequest
    from app.services.research_data.backtest_qlib import (
        BacktestArtifactStore,
        QlibResearchBacktestEngine,
        load_target_weight_series,
        weights_for_date,
    )
    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.contracts import DatasetDefinition
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.experiment import (
        ExperimentManifestStore,
        ExperimentRunner,
        ExperimentSpec,
    )
    from app.services.research_data.ingest.build_golden import (
        GOLDEN_DATASET_CODE,
        build_golden_dataset,
    )
    from app.services.research_data.model_training import (
        ModelArtifactStore,
        ModelTrainSpec,
        ModelTrainer,
        builtin_lgb_baseline_model,
    )
    from app.services.research_data.qlib_adapter import (
        QlibAdapter,
        ResearchDatasetSpec,
        SegmentRange,
        SegmentSpec,
        builtin_qd_standard_processor,
    )
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
    from app.services.research_data.registry import LocalJsonRegistry
    from app.services.research_data.signal import (
        EqualWeightPortfolio,
        SignalPipeline,
        SignalRunSpec,
        TopKStrategy,
    )
    from app.services.research_data.signal.artifact_store import SignalArtifactStore

    root = Path(tempfile.mkdtemp(prefix="qd_phase3b_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(root / "cache")
    os.environ["MLFLOW_TRACKING_URI"] = f"file:{root / 'mlruns'}"

    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    start, end = date(2024, 1, 1), date(2024, 6, 30)
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=start,
        end=end,
        universe_version="2024.06",
        snapshot_id="snap_phase3b_verify",
        use_fixture=True,
        status="validated",
    )
    query = DataQuery(store, registry)
    materializer = DefaultQlibMaterializer(
        query, cache_root=root / "qlib_cache", start=start, end=end
    )
    registry.upsert_processor(builtin_qd_standard_processor())
    registry.upsert_model(builtin_lgb_baseline_model())

    handle = query.dataset(golden["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_3b_verify",
        name="phase3b verify",
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
    dataset_ref = f"{GOLDEN_DATASET_CODE}@v1_3b_verify"

    adapter = QlibAdapter(
        query,
        materializer=materializer,
        registry=registry,
        dataset_cache_root=root / "ds_cache",
        start=start,
        end=end,
    )
    trainer = ModelTrainer(
        adapter, registry, artifact_store=ModelArtifactStore(root=root / "model_art")
    )
    signals = SignalPipeline(
        registry, artifact_store=SignalArtifactStore(root=root / "signal_art")
    )
    runner = ExperimentRunner(
        adapter,
        registry,
        model_trainer=trainer,
        signal_pipeline=signals,
        manifest_store=ExperimentManifestStore(root=root / "exp_art"),
    )

    segments = SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )
    spec = ExperimentSpec(
        name="phase3b_verify",
        train=ModelTrainSpec(
            dataset_spec=ResearchDatasetSpec(dataset_ref=dataset_ref, segments=segments),
            model=builtin_lgb_baseline_model(),
            seed=42,
        ),
        signal=SignalRunSpec(
            strategy=TopKStrategy(k=2),
            portfolio=EqualWeightPortfolio(),
        ),
    )
    exp_result = runner.run(spec)
    experiment = registry.get_experiment(exp_result.experiment_id)

    exec_p, price_p, cost_p, rules = research_qlib_relaxed()
    request = BacktestRequest.from_experiment(
        experiment,
        start_date="2024-05-01",
        end_date="2024-06-30",
        initial_capital=1_000_000.0,
        engine="qlib",
        execution_policy=exec_p,
        market_price_policy=price_p,
        cost_policy=cost_p,
        trading_rule=rules,
    ).model_copy(update={"benchmark": None, "dataset_ref": dataset_ref})

    eng = QlibResearchBacktestEngine(
        adapter,
        registry,
        artifact_store=BacktestArtifactStore(root=root / "bt_art"),
    )
    a = eng.run(request)
    b = eng.run(request)

    signal_art = registry.get_artifact(exp_result.signal_artifact_id)
    series = load_target_weight_series(signal_art)
    day = series.index.get_level_values("datetime")[0]
    mapped = weights_for_date(series, day) or {}

    import pyarrow.parquet as pq

    pos_df = pq.read_table(
        Path(signal_art.storage_uri) / "target_positions.parquet"
    ).to_pandas()
    day_str = day.strftime("%Y-%m-%d")
    day_rows = pos_df[pos_df["trading_date"].astype(str).str[:10] == day_str]
    weight_ok = True
    for _, row in day_rows.iterrows():
        qid = to_qlib_instrument(str(row["instrument_key"])).lower()
        if qid not in mapped or abs(mapped[qid] - float(row["target_weight"])) > 1e-9:
            weight_ok = False
            break

    fp = compute_request_fingerprint(request)
    equity_ok = False
    if a.equity_curve and b.equity_curve:
        equity_ok = abs(a.equity_curve[-1].equity - b.equity_curve[-1].equity) < 1e-4
    else:
        equity_ok = a.metrics.total_return == b.metrics.total_return

    checks = {
        "minimal": {
            "ok": bool(a.equity_curve or a.metrics.total_return is not None),
            "equity_points": len(a.equity_curve),
            "result_id": a.result_id,
        },
        "dataset_hash": {
            "ok": a.dataset_hash == request.dataset_hash == experiment.dataset_hash,
        },
        "experiment_trace": {
            "ok": bool(
                experiment.dataset_ref
                and experiment.model_artifact_id
                and experiment.signal_artifact_id
            ),
            "experiment_id": a.experiment_id,
        },
        "double_run": {
            "ok": a.request_fingerprint == b.request_fingerprint == fp and equity_ok,
            "fingerprint": fp[:16],
        },
        "weight_align": {"ok": weight_ok and bool(mapped)},
        "completeness": {
            "ok": bool(a.result_id and a.artifact_uris and a.metrics is not None),
            "artifact_uris": list(a.artifact_uris.keys()),
        },
    }
    ok = all(v.get("ok") for v in checks.values())
    print(
        json.dumps(
            {"ok": ok, "root": str(root), "checks": checks},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
