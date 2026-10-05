#!/usr/bin/env python3
"""Phase 2E 验收：Prediction → Signal → TargetPosition（合成预测，无需 LightGBM）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase2e_signal.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def main() -> int:
    from app.services.research_data.contracts import PredictionRecord
    from app.services.research_data.registry import LocalJsonRegistry
    from app.services.research_data.signal import (
        EqualWeightPortfolio,
        SignalPipeline,
        SignalRunSpec,
        ThresholdStrategy,
        TopKStrategy,
        normalize_predictions,
        order_intents_from_targets,
    )

    root = Path(tempfile.mkdtemp(prefix="qd_phase2e_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(root / "cache")
    registry = LocalJsonRegistry(root=root / "registry")

    rows = [
        ("CNStock:000001", 0.12),
        ("CNStock:000002", 0.08),
        ("CNStock:600000", 0.03),
        ("CNStock:600519", -0.05),
    ]
    preds = [
        PredictionRecord(
            instrument_key=inst,
            trading_date="2026-09-30",
            prediction=val,
            model_version="lgb_baseline@1",
            dataset_hash="ds_verify_2e",
            bundle_hash="bundle_verify_2e",
            snapshot_id="snap_verify_2e",
        )
        for inst, val in rows
    ]
    preds = normalize_predictions(preds)

    pipe = SignalPipeline(registry)
    topk = pipe.run(
        preds,
        SignalRunSpec(strategy=TopKStrategy(k=2), portfolio=EqualWeightPortfolio()),
    )
    thr = pipe.run(
        preds,
        SignalRunSpec(
            strategy=ThresholdStrategy(min_score=0.10),
            portfolio=EqualWeightPortfolio(),
        ),
    )

    checks: dict = {}
    # Prediction 追溯
    checks["prediction"] = {
        "ok": bool(preds[0].prediction_id)
        and preds[0].model_version == "lgb_baseline@1"
        and preds[0].dataset_hash == "ds_verify_2e",
    }
    # 策略解耦
    topk_long = sorted(
        s.instrument_key for s in topk.signals if s.direction == "LONG"
    )
    thr_long = sorted(
        s.instrument_key for s in thr.signals if s.direction == "LONG"
    )
    checks["strategy_decouple"] = {
        "ok": topk_long != thr_long and len(topk_long) == 2 and len(thr_long) == 1,
        "topk_long": topk_long,
        "threshold_long": thr_long,
    }
    # 时间语义
    time_ok = all(
        s.execution_time > s.signal_time and s.knowledge_time == s.signal_time
        for s in topk.signals
    )
    checks["time_semantics"] = {"ok": time_ok}
    # TargetPosition
    gross = sum(float(p.target_weight or 0) for p in topk.positions)
    weight_ok = abs(gross + topk.cash_weight - 1.0) < 1e-9
    checks["target_position"] = {
        "ok": weight_ok and len(topk.positions) == 2,
        "cash_weight": topk.cash_weight,
        "n_positions": len(topk.positions),
    }
    # 确定性
    topk2 = pipe.run(
        preds,
        SignalRunSpec(strategy=TopKStrategy(k=2), portfolio=EqualWeightPortfolio()),
    )
    checks["determinism"] = {
        "ok": topk.artifact_id == topk2.artifact_id,
        "artifact_id": topk.artifact_id,
    }
    # OrderIntent 仅契约；pipeline 不下单
    intents = order_intents_from_targets(topk.positions)
    checks["order_intent_contract"] = {
        "ok": len(intents) == len(topk.positions),
        "n_intents": len(intents),
        "pipeline_emits_orders": False,
    }
    # Registry
    run = registry.get_signal_run(topk.signal_run_id)
    checks["registry"] = {
        "ok": run.artifact_id == topk.artifact_id,
        "strategy_version": run.strategy_version,
    }

    ok = all(bool(c.get("ok")) for c in checks.values())
    print(json.dumps({"ok": ok, "checks": checks, "root": str(root)}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
