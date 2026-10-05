# Phase 2D — Model Training (LightGBM)

> **Status:** Phase 2D implemented.
> Phase 2E Signal / 2F Experiment orchestration remain out of scope.

## 1. Goal

```text
ResearchDatasetSpec
        ↓
QlibAdapter.build_dataset → DatasetH
        ↓
LightGBMModelAdapter.fit(train) / evaluate(valid) / predict(test)
        ↓
Artifact (model.bin + metadata + predictions.parquet)
        ↓
Registry + PredictionRecord
```

**Only engine:** LightGBM via `qlib.contrib.model.gbdt.LGBModel` (wrapped by `LightGBMModelAdapter`).

## 2. Contracts

| Type | Role |
| --- | --- |
| `ModelDefinition` | code / version / engine / config |
| `ModelTrainSpec` | dataset_spec + model + seed |
| `PredictionRecord` | test predictions with hash chain |
| `ArtifactRecord` | D1 index; bytes under `qd/artifacts/model/` |

## 3. Train / valid / test

- Model **fit** uses Qlib `train` (+ internal `valid` for early stopping only)
- **Valid** metrics: MSE / rank IC (no refit)
- **Test**: `predict` only; dates must fall in test segment
- Processor fit-on-train unchanged from Phase 2C

## 4. Artifact id

```text
artifact_id = sha256(bundle_hash | model_ref | config_digest | seed | model_trainer@1)
```

Local layout:

```text
{research_cache}/qd/artifacts/model/{artifact_id}/
  model.bin
  metadata.json
  predictions.parquet
```

## 5. Commands

```bash
cd backend_api_python
# macOS: if LightGBM fails with libomp
brew install libomp

QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2d_model.py

MLFLOW_DISABLE_AGENT_HINT=1 \
  python -m pytest tests/research_data/test_phase2d_*.py -q
```

Exit codes: **0** PASS / **1** FAIL / **2** missing pyqlib or LightGBM.

## 6. Non-goals

```text
❌ XGBoost / CatBoost / PyTorch / Transformer
❌ Signal / TargetPosition / OrderIntent
❌ Full MLflow experiment platform (Phase 2F)
```

## 7. Next

Phase 2E — Prediction / Signal (Prediction → Signal, not orders).
