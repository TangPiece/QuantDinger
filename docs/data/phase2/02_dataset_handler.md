# Phase 2B — Dataset & DataHandler

> **Status:** Phase 2B implemented.
> Phase 2C Processor pipeline / Model / Signal remain out of scope.

## 1. Goal

```text
DatasetDefinition (SSOT)
      + ResearchDatasetSpec (segments / label)
        ↓
QuantDingerQLibHandler
        ↓
DatasetH (train / valid / test)
```

## 2. Runtime specs (not Domain Contract)

`ResearchDatasetSpec` / `SegmentSpec` live in `qlib_adapter/specs.py`.

Hard rule: `train.end < valid.start < … < test.start` (no overlap / shuffle).

Default label: `fwd_ret@1` → `Ref($close, -5) / $close - 1`.

## 3. Components

| Module | Role |
| --- | --- |
| `label_adapter.py` | Negative `Ref` / forward return (Feature path still rejects these) |
| `handler.py` | `QuantDingerQLibHandler` |
| `dataset_cache.py` | `{cache}/qlib-dataset-cache/{artifact_id}/` |
| `dataset_adapter.py` | `build_qd_handler` / `build_dataset(spec)` |

## 4. Cache separation

| Cache | Path |
| --- | --- |
| Materializer | `qlib-cache/{materialization_id}/` |
| Dataset artifact | `qlib-dataset-cache/{artifact_id}/` |

`artifact_id = sha256(bundle_hash | segments | label | adapter@1)`

## 5. Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2b_dataset.py

MLFLOW_DISABLE_AGENT_HINT=1 \
  python -m pytest tests/research_data/test_phase2b_*.py -q
```

## 6. Non-goals

```text
❌ Alpha158 / LightGBM / Signal / Backtest
❌ Changing Phase 1 DatasetDefinition fields for segments
```

## 7. Next

Phase 2C — [Processor Pipeline](03_processor_pipeline.md) (fit-on-train, `qd_standard@1`).
