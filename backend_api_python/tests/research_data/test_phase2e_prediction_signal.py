"""Phase 2E：Prediction → Signal → TargetPosition（解耦 / 时间 / 确定性）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.contracts import PredictionRecord
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.signal import (
    EqualWeightPortfolio,
    SignalPipeline,
    SignalRunSpec,
    ThresholdStrategy,
    TopKStrategy,
    compute_prediction_id,
    normalize_predictions,
    order_intents_from_targets,
    prediction_fingerprint,
)


def _synth_predictions() -> list[PredictionRecord]:
    """合成截面预测（同日四标的），无需 LightGBM。"""
    rows = [
        ("CNStock:000001", 0.12),
        ("CNStock:000002", 0.08),
        ("CNStock:600000", 0.03),
        ("CNStock:600519", -0.05),
    ]
    out: list[PredictionRecord] = []
    for inst, val in rows:
        out.append(
            PredictionRecord(
                instrument_key=inst,
                trading_date="2026-09-30",
                prediction=val,
                model_version="lgb_baseline@1",
                dataset_hash="ds_hash_abc",
                bundle_hash="bundle_hash_xyz",
                snapshot_id="snap_test",
            )
        )
    return out


@pytest.fixture()
def signal_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """隔离 research_cache + Local Registry。"""
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    return {"registry": registry, "root": tmp_path}


def test_normalize_prediction_id_and_traceability(signal_env):
    preds = normalize_predictions(_synth_predictions())
    assert all(p.prediction_id for p in preds)
    assert all(p.model_version == "lgb_baseline@1" for p in preds)
    assert all(p.dataset_hash == "ds_hash_abc" for p in preds)
    expected = compute_prediction_id(
        model_version="lgb_baseline@1",
        instrument_key="CNStock:000001",
        trading_date="2026-09-30",
        dataset_hash="ds_hash_abc",
    )
    assert preds[0].prediction_id == expected


def test_topk_vs_threshold_decoupled(signal_env):
    """同一 Prediction 可用不同 Signal Strategy。"""
    registry = signal_env["registry"]
    preds = _synth_predictions()
    pipe = SignalPipeline(registry)

    topk = pipe.run(preds, SignalRunSpec(strategy=TopKStrategy(k=2), portfolio=EqualWeightPortfolio()))
    thr = pipe.run(
        preds,
        SignalRunSpec(
            strategy=ThresholdStrategy(min_score=0.05),
            portfolio=EqualWeightPortfolio(),
        ),
    )

    topk_long = {s.instrument_key for s in topk.signals if s.direction == "LONG"}
    thr_long = {s.instrument_key for s in thr.signals if s.direction == "LONG"}
    assert topk_long == {"CNStock:000001", "CNStock:000002"}
    assert thr_long == {"CNStock:000001", "CNStock:000002"}
    # Threshold 在 min_score=0.10 时与 TopK(2) 分化
    thr2 = pipe.run(
        preds,
        SignalRunSpec(
            strategy=ThresholdStrategy(min_score=0.10),
            portfolio=EqualWeightPortfolio(),
        ),
    )
    thr2_long = {s.instrument_key for s in thr2.signals if s.direction == "LONG"}
    assert thr2_long == {"CNStock:000001"}
    assert thr2_long != topk_long
    assert topk.artifact_id != thr2.artifact_id


def test_signal_time_semantics(signal_env):
    registry = signal_env["registry"]
    result = SignalPipeline(registry).run(
        _synth_predictions(),
        SignalRunSpec.default_topk(k=2),
    )
    for s in result.signals:
        assert s.signal_time.tzinfo is not None
        assert s.knowledge_time == s.signal_time
        assert s.execution_time > s.signal_time


def test_target_position_weights_and_cash(signal_env):
    registry = signal_env["registry"]
    result = SignalPipeline(registry).run(
        _synth_predictions(),
        SignalRunSpec(
            strategy=TopKStrategy(k=2),
            portfolio=EqualWeightPortfolio(max_gross=0.6),
        ),
    )
    gross = sum(float(p.target_weight or 0.0) for p in result.positions)
    assert abs(gross + result.cash_weight - 1.0) < 1e-9
    assert len(result.positions) == 2
    assert all(p.portfolio_id for p in result.positions)
    assert all(p.signal_id for p in result.positions)


def test_order_intent_mapper_contract_only_not_in_pipeline(signal_env):
    registry = signal_env["registry"]
    pipe = SignalPipeline(registry)
    with pytest.raises(ValueError, match="does not emit OrderIntent"):
        pipe.run(
            _synth_predictions(),
            SignalRunSpec.default_topk(k=2),
            emit_order_intents=True,
        )
    result = pipe.run(_synth_predictions(), SignalRunSpec.default_topk(k=2))
    intents = order_intents_from_targets(result.positions)
    assert intents
    assert all(i.side == "BUY" for i in intents)
    # 无 broker / exchange 运行时依赖（仅检查 import，忽略文档字符串）
    import ast
    import app.services.research_data.signal.order_intent_mapper as m

    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    joined = " ".join(imported).lower()
    assert "broker" not in joined
    assert "exchange" not in joined
    assert "live_trading" not in joined
    assert "strategy_v2" not in joined


def test_deterministic_artifact_id(signal_env):
    registry = signal_env["registry"]
    pipe = SignalPipeline(registry)
    spec = SignalRunSpec.default_topk(k=2)
    a = pipe.run(_synth_predictions(), spec)
    b = pipe.run(_synth_predictions(), spec)
    assert a.artifact_id == b.artifact_id
    assert a.prediction_fingerprint == prediction_fingerprint(
        normalize_predictions(_synth_predictions())
    )
    run = registry.get_signal_run(a.signal_run_id)
    assert run.artifact_id == a.artifact_id
    assert run.strategy_version == "topk@1"
