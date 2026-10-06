# Phase 4A — Factor Definition & Registry

## Principle

**Factor is the research semantic of Feature.** Do not create a parallel D1 `factor` table that conflicts with trading `services.factors.FactorDefinition`.

```text
FeatureDefinition (D1 feature)
   └── research role = Factor Lab asset
        ├── Factor Version (code@version, immutable)
        ├── Factor Dependency (feature_dependency)
        ├── factor_hash
        └── FactorDataset → R2 Parquet + Manifest
```

Trading-side factor registry (`app.services.factors`) is out of scope and must not be imported by `research_data.factor_lab`.

## Domain fields

`FeatureDefinition` (extended):

| Field | Notes |
| --- | --- |
| code / version / name / expression | Identity |
| factor_type | TECHNICAL … CUSTOM |
| computation_engine | qlib / quantdinger / duckdb / polars / level2 |
| engine_version | Engine build/version string |
| information_policy | PIT_SAFE / NON_PIT / UNKNOWN |
| schema_version | factor_daily_long@1 or factor_daily_wide@1 |
| dependencies | `type:code` strings |
| factor_hash | Content hash at register |
| price_policy / processor_ref | Enter hash |
| backend | Where values live: r2_factor / d1_l2_factors / computed |

## factor_hash

Canonical JSON over: code, version, expression, schema_version, sorted dependencies, processor_ref, price_policy, computation_engine, engine_version, factor_type, frequency, information_policy, `qd_factor_lab@1`.

Same definition → same hash. Change definition → bump **version** (immutability enforced).

## Dependencies

Whitelist types: `market`, `fundamental`, `corporate_action`, `trading_status`, `universe`, `level2`, `factor`, `other`.

Format: `type:code` (e.g. `factor:momentum_20d@1.0.0`). Cycles forbidden. D1 `feature_dependency` is written on upsert; `get_feature` restores them.

## PIT

- `PIT_SAFE`: must depend on `fundamental` (or equivalent PIT source); `available_time <= knowledge_time` when computing (4B).
- `UNKNOWN`: may register; **`validate_for_backtest()` → False** (blocked from formal backtest).
- `NON_PIT`: allowed for technical factors that do not use delayed fundamentals.

## Factor Dataset

Registry: `FactorDatasetRecord` binds `factor_ref`, `factor_hash`, `dataset_hash`, `snapshot_id`, universe, frequency, date range, layout.

```text
factor_dataset_id = sha256(factor_hash|dataset_hash|snapshot|universe|freq|start|end|layout)[:32]
```

R2 / cache:

```text
qd/factor/daily/factor_set={code}@{version}/year=YYYY/month=MM/part-*.parquet
qd/dataset/factor/{factor_dataset_id}/manifest.json
```

Manifest required: factor_code/version/hash, dataset_hash, snapshot_id, schema_version, min/max date, universe, row_count, checksum, layout, engine, engine_version.

## Wide vs Long

| Case | Layout |
| --- | --- |
| Single / sparse / PIT fundamental | **long** (`factor_daily_long@1`) |
| Large standard sets (Alpha158-like) | **wide** (`factor_daily_wide@1`) |

4A defines schema + rules; 4B performs computation.

## Compatibility

- Phase 1 `DataQuery.feature` / `write_factor_long` unchanged in behavior.
- Phase 2 `DatasetDefinition.features` remains OHLCV expression whitelist until 4B+ bridge.
- Phase 3 backtest engines untouched.
- D1 migration: `workers/qd-research-d1/migrations/0002_factor_lab.sql`.

## Package

```text
backend_api_python/app/services/research_data/factor_lab/
```

API: `register_factor`, `get_factor`, `register_factor_dataset`, `compute_factor_hash`, `validate_for_backtest`, `FactorDatasetArtifactStore`.
