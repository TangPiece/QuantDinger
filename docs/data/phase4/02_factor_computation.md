# Phase 4B — Factor Computation Engine

## Principle

```text
FactorDefinition (4A)
  → Dependency DAG
  → ComputePlan + PITComputeContext
  → FactorComputeEngine (Polars | Qlib | Level2 | DuckDB)
  → FactorFrame
  → write_factor_* + Manifest
  → FactorDatasetRecord (immutable)
```

Factor Lab **computes** immutable FactorDatasets. Evaluation (IC / RankIC / …) is Phase 4C+.

## Package

```text
backend_api_python/app/services/research_data/factor_lab/compute/
  protocol.py           # FactorComputeEngine, ComputePlan, PITComputeContext, FactorFrame
  hash.py               # plan_hash / result_dataset_hash
  resolver.py           # Dependency DAG（拓扑序）
  planner.py            # Capability → engine → ComputePlan
  orchestrator.py       # FactorComputeService.run
  dsl.py                # 最小表达式 → market panel
  writers.py            # long/wide + register + manifest
  engines/
    polars_engine.py    # 主路径（pandas DSL；polars 可选）
    quantdinger_engine.py
    duckdb_engine.py
    qlib_engine.py      # importorskip / FeatureAdapter 薄适配
    level2_engine.py    # enrich_panel / panel → FactorFrame
```

API（经 `factor_lab` 导出）：`FactorComputeService`, `build_compute_plan`, `resolve_dependency_dag`, `PITComputeContext`, `compute_result_dataset_hash`.

## Domain contracts

### ComputePlan

`factor_ref`, `factor_hash`, `plan_hash`, `snapshot_id`, `dataset_hash`（输入钉住）, `engine`, `engine_version`, `dependency_order`, frequency / universe / date range, `knowledge_time`, `price_policy`, `processor_ref`, `layout`, `schema_version`, `expression`, `metadata`.

### PITComputeContext

tz-aware UTC `knowledge_time` + snapshot / exchange / universe / price_policy / date window / optional `canonical_dataset_hash`.

`PIT_SAFE` factors **require** `knowledge_time`; fundamental rows with `available_time > knowledge_time` must not appear.

### FactorFrame

Long: `instrument_key`, `trading_date`, `value`. Wide: multi factor columns. Writer converts to Arrow before parquet.

## Dependency DAG

Built on 4A `validate_dependencies`:

- Nodes: factor refs + data dependency types
- Edges: factor→factor, factor→data
- Fail: cycles, missing factor, illegal type, factor without `@version`
- `dependency_order` enters `plan_hash`

## Engine selection (capability)

| Condition | Engine |
| --- | --- |
| `computation_engine=level2` or deps contain `level2` | Level2FactorEngine |
| `computation_engine=qlib` or expression has `$` / `Ref($` | QlibFactorEngine |
| `computation_engine=duckdb` | DuckDBFactorEngine |
| default / `polars` / `quantdinger` | PolarsFactorEngine |

## Writer + immutability

- `write_factor_long` / `write_factor_wide`
- `result_dataset_hash` = sha256(factor_hash \| snapshot \| input_dataset_hash \| deps \| processor \| price_policy \| engine \| engine_version \| schema \| date_range \| knowledge_time)
- `factor_dataset_id` = 4A `compute_factor_dataset_id`（含 layout）
- Same id → idempotent skip; different inputs → new id, **never overwrite** old parquet
- After write: Manifest + `upsert_factor_dataset` + artifact

Layout (unchanged from 4A):

```text
qd/factor/daily/factor_set={code}@{version}/year=/month=/part-*.parquet
qd/dataset/factor/{factor_dataset_id}/manifest.json
```

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4b_factor_compute.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4b_factor_compute.py -q \
  --confcutdir=tests/research_data
```

Checks: DAG/cycle/missing · plan determinism · hash/repro · version isolation · PIT leakage · schema/manifest · Polars↔DuckDB tolerance · Level2 column map.

## Non-goals

```text
❌ IC / RankIC / ICIR / Group Return / Decay / Neutralization
❌ Factor Lab UI / RD-Agent / online factor service
❌ Full Alpha158 generator
❌ Modify Phase 3 Production Backtest
❌ Modify l2_factors Worker
❌ Qlib types in Domain
```
