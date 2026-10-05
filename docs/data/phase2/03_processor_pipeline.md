# Phase 2C — Processor Pipeline

> **Status:** Phase 2C implemented.
> Phase 2D Model Training (LightGBM) is next; Signal / Backtest remain out of scope.

## 1. Goal

```text
DatasetDefinition.processor (code@version)
        ↓
Registry ProcessorDefinition.pipeline
        ↓
ProcessorAdapter → Qlib learn/infer
        ↓
DataHandlerLP (fit on train only)
        ↓
Model-ready features
```

Core rule: **Processor is a versioned research asset**, not ad-hoc Python in Dataset build.

## 2. First-batch steps

| QD name | Qlib class | Needs fit window |
| --- | --- | --- |
| Dropna | `DropnaProcessor` | No |
| Fillna | `Fillna` | No |
| Winsorize / Clip | `RobustZScoreNorm` (`clip_outlier=True`) | **Yes** (train) |
| CSZScore | `CSZScoreNorm` | No (per-day CS) |
| MinMax | `MinMaxNorm` | **Yes** (train) |

Builtin standard pipeline: `qd_standard@1`

```text
Fillna → RobustZScoreNorm(clip) → CSZScoreNorm
```

True percentile Winsorize is **not** in 2C (Qlib has no dedicated class).

## 3. Fit / transform lifecycle

```text
ResearchDatasetSpec.segments.train
        ↓
fit_start / fit_end  (default = train)
        ↓
inject only into RobustZScore / MinMax
        ↓
transform train / valid / test
```

- `learn_processors` ≡ `infer_processors` (same definition)
- Processors that need fit **must** use `ResearchDatasetSpec`; `build_handler(str)` raises
- PIT: Handler path still must not call `DataQuery.fundamental`

## 4. Hash & immutability

| Layer | Behavior |
| --- | --- |
| Domain `dataset_hash` | Includes `processor` ref `code@version` (Phase 1 algorithm unchanged) |
| Registry | Same `code@version` **cannot** change `pipeline` (bump version) |
| `bundle_hash` | `sha256(dataset_hash \| qlib_adapter@2 \| processor_ref \| pipeline_digest)` |

`pipeline_digest = sha256(canonical_json(pipeline))` or `"none"`.

## 5. Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2c_processor.py

MLFLOW_DISABLE_AGENT_HINT=1 \
  python -m pytest tests/research_data/test_phase2c_*.py -q
```

## 6. Non-goals

```text
❌ LightGBM / Model training (Phase 2D)
❌ Alpha158 / Signal / Backtest
❌ Changing Phase 1 compute_dataset_hash algorithm
❌ True percentile Winsorize
```

## 7. Next

Phase 2D — Model Training (LightGBM end-to-end: Dataset → Processor → Prediction → MLflow).
