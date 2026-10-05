# Phase 2E — Prediction & Signal

> **Status:** Phase 2E implemented.
> Phase 2F Experiment & Reproducibility — **implemented** → [06_experiment_reproducibility.md](06_experiment_reproducibility.md).

## 1. Goal

```text
PredictionRecord
        ↓
SignalStrategy (TopK / Threshold)
        ↓
Signal  (+ signal_time / knowledge_time / execution_time)
        ↓
EqualWeightPortfolio
        ↓
TargetPosition  (+ cash_weight in metadata)
        ↓
OrderIntent  (contract-only mapper; NOT called by pipeline)
```

**Prediction ≠ Signal.** Model outputs scores; strategies interpret them.

## 2. Contracts

| Type | Role |
| --- | --- |
| `PredictionRecord` | Domain prediction + `prediction_id` / `snapshot_id` / hashes |
| `Signal` | direction / score / three timestamps / strategy_version |
| `TargetPosition` | portfolio_id / weight / signal_id 追溯 |
| `OrderIntent` | BUY/SELL 契约字段；**不接 Broker** |
| `SignalRunRecord` | Local Registry 索引一次 signal 运行 |

时间约定（日频 CN，`timeutil.resolve_signal_times`）：

- `signal_time` = `knowledge_time` = `trading_date` 15:00 Asia/Shanghai → UTC
- `execution_time` = **下一自然日** 09:30 Asia/Shanghai → UTC（交易日历留给 Phase 3）

## 3. Package

`app/services/research_data/signal/`

- `TopKStrategy` / `ThresholdStrategy` — 同一 Prediction 可换策略
- `EqualWeightPortfolio` — LONG 等权；`cash_weight = 1 - max_gross`
- `SignalPipeline.run` — 默认 **不** 调用 `order_intents_from_targets`
- Artifact：`qd/artifacts/signal/{artifact_id}/`（signals.parquet / target_positions.parquet / metadata.json）

```text
signal_artifact_id = sha256(prediction_fingerprint | strategy_digest | portfolio_digest | signal_pipeline@1)
```

## 4. Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase2e_signal.py

QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python -m pytest tests/research_data/test_phase2e_*.py -q \
  --confcutdir=tests/research_data
```

Exit codes: **0** PASS / **1** FAIL（合成 Prediction，无需 LightGBM）。

## 5. Non-goals

```text
❌ Broker / 实盘下单
❌ 撮合、手续费、滑点、涨跌停、整手
❌ 真实 T+1 交易日历与回测
❌ 复杂组合优化
❌ LongShort / Quantile 策略实现（仅留 Protocol）
```

## 6. Next

Phase 2F — Experiment & Reproducibility — **implemented** → [06_experiment_reproducibility.md](06_experiment_reproducibility.md).

Next: Phase 3A — Backtest Contract.