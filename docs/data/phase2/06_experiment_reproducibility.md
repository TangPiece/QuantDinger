# Phase 2F — Experiment & Reproducibility

> **Status:** Phase 2F implemented. **Phase 2 complete.**
> Next: Phase 3A — Backtest Contract (do not extend Phase 2 further).

## 1. Goal

```text
ExperimentSpec
        ↓
ModelTrainer.train → Prediction
        ↓
SignalPipeline.run → Signal / TargetPosition
        ↓
manifest.json + Registry Experiment + MLflow Run
```

Give one `experiment_id` and recover: dataset_hash, features, processor, model, strategy, metrics, artifacts.

## 2. Contracts

| Type | Role |
| --- | --- |
| `ExperimentDefinition` | Domain 顶层：refs + metrics + `repro_fingerprint` + `manifest_uri` |
| `ExperimentManifest` | 落盘快照（非 SSOT） |
| `ExperimentSpec` | `ModelTrainSpec` + `SignalRunSpec` + seed |

`experiment_id = exp_{repro_fingerprint[:32]}`（内容寻址）。

## 3. Artifact layout

```text
qd/artifacts/model/{id}/          # Phase 2D（不变）
qd/artifacts/signal/{id}/         # Phase 2E（不变）
qd/artifacts/experiments/{experiment_id}/manifest.json   # Phase 2F 新增
```

## 4. Metrics（无回测收益）

- Valid：`valid_mse` / `valid_mae` / `valid_rmse` / `valid_rank_ic`（兼 `valid_ic`）
- Signal：`long_count` / `short_count` / `flat_count`
- **禁止**：CAGR / Sharpe / MaxDrawdown / Commission / Slippage

## 5. Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2f_experiment.py

QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python -m pytest tests/research_data/test_phase2f_*.py -q \
  --confcutdir=tests/research_data
```

Exit codes: **0** PASS / **1** FAIL / **2** missing pyqlib or LightGBM.

## 6. Non-goals

```text
❌ CAGR / Sharpe / MaxDrawdown / Commission / Slippage
❌ Broker / 撮合 / 实盘
❌ 搬迁 model/ → models/
❌ 自研 Tracking 替代 MLflow
❌ Phase 3 Backtest
```

## 7. Next

**Phase 3A — Backtest Contract**（Qlib Research Backtest 与 QuantDinger Production Backtest 统一接口）。Phase 2 到此结束。
