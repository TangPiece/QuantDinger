# Phase 2A — Qlib Adapter Core

> **Status:** Phase 2A implemented.
> Phase 2B Dataset segments / 2C Processor pipeline / Model / Signal remain out of scope.

## 1. Goal

Establish the formal boundary:

```text
QuantDinger Domain
       ↓
Qlib Adapter
       ↓
Qlib API
```

Business code must **not** call `qlib.init` directly.

## 2. Package

`backend_api_python/app/services/research_data/qlib_adapter/`

| Module | Role |
| --- | --- |
| `runtime.py` | `QlibRuntime` — process-level `qlib.init` |
| `version_resolver.py` | `dataset_hash` + `bundle_hash` |
| `feature_adapter.py` | QuantDinger expr → Qlib expression |
| `processor_adapter.py` | ProcessorDefinition → Qlib processors |
| `dataset_adapter.py` | `QlibAdapter` facade (`build_handler` / `build_dataset`) |

## 3. Hash layering

| Hash | Contents | Purpose |
| --- | --- | --- |
| `dataset_hash` | Domain definition + snapshot + schema + processor ref + `materializer_version=none` + price_policy | Canonical / experiment fact key (unchanged from Phase 1) |
| `materialization_id` | `dataset_hash` + `qlib_materializer@1` | Local Qlib cache dir |
| `bundle_hash` | `dataset_hash` + `qlib_adapter@1` + resolved processor | Adapter experiment reproducibility |

## 4. Feature whitelist (2A)

- Atomic: `$open/$high/$low/$close/$volume/$amount` (+ vwap)
- Ops: `Ref`, `Mean`, `Std`, `Max`, `Min`, `Slope`
- Rejected: `Rank`, return formulas, Alpha158

## 5. Processor whitelist (2A)

Registry CRUD: `upsert_processor` / `get_processor`.

- `identity@1` → empty processors
- `DropnaProcessor`
- `CSZScoreNorm` (`cs_zscore@1`)

Train and infer use the **same** processor config.

## 6. Facade usage

```python
from app.services.research_data.qlib_adapter import QlibAdapter

adapter = QlibAdapter(query, materializer=mat, registry=registry, start=..., end=...)
bundle = adapter.resolve("cn_stock_daily@v1")
handler = adapter.build_handler("cn_stock_daily@v1", start=..., end=...)
df = handler.fetch(col_set="feature")
```

## 7. Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2a_adapter.py

MLFLOW_DISABLE_AGENT_HINT=1 \
  python -m pytest tests/research_data/test_qlib_adapter_*.py -q
```

## 8. Non-goals

```text
❌ Alpha158 / LightGBM / Model training
❌ Signal / TargetPosition / Backtest
❌ Full train/valid/test segments (Phase 2B)
❌ Full Dropna→Winsorize→CSZScore pipeline polish (Phase 2C)
❌ Rank / return Feature DSL
```

## 9. Next

Phase 2B — Dataset / DataHandler segments (`fit_*` / `valid_*` / `test_*`).
