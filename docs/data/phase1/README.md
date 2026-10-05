# Phase 1 — Research Data Platform Contracts

> **Status:** Phase 1C complete (Qlib Materializer + derived cache validation).
> Qlib Adapter / Factor Lab / Backtest still out of scope.
>
> **Audience:** Engineers implementing QuantDinger × Qlib research data foundation.
>
> **Code:** `workers/qd-research-d1/`, `backend_api_python/app/services/research_data/`.

This package locks the contracts for:

1. Storage architecture and layered SSOTs
2. D1 `qd_research` registry schema
3. R2 research layout
4. Parquet schemas
5. Domain / `DataQuery` Python contracts
6. Research consistency and leakage rules

## Reading order

1. [01_storage_architecture.md](01_storage_architecture.md)
2. [02_d1_research_schema.md](02_d1_research_schema.md)
3. [03_r2_layout.md](03_r2_layout.md)
4. [04_parquet_schemas.md](04_parquet_schemas.md)
5. [05_contracts.md](05_contracts.md)
6. [06_research_consistency.md](06_research_consistency.md)
7. [07_phase1b_validation.md](07_phase1b_validation.md) — Golden Dataset / DataQuery 验收
8. [08_qlib_materialization.md](08_qlib_materialization.md) — Qlib Materializer / 派生缓存

## Layered SSOT (locked)

> **QuantDinger Domain Contract is the semantic SSOT for research and data access.
> Physical data is owned per domain by PostgreSQL, R2, Baidu Netdisk, and existing `l2_factors`.**

| Layer | Role | SSOT |
| --- | --- | --- |
| Domain Contract | Fields, PIT rules, versions, query protocol | This package (+ future Pydantic modules) |
| Trading operations | Instruments, business universes, trading-side fundamentals | **PostgreSQL** |
| Research fact data | Market, PIT, universe snapshots, CA, status, research factors | **R2 Canonical (+ `qd/factor/`)** |
| Level2 raw archive | Tick / order / quote detail | **Baidu Netdisk** |
| Level2 hot factors | Chart / online factor queries | **D1 `l2_factors`** |
| Research registry | Dataset / Feature / Experiment / Version / Snapshot / Artifact index | **D1 `qd_research`** |
| Local | Hot cache, DuckDB, Qlib derived cache | Rebuildable; never SSOT |

### What each system is *not*

- Domain Contract does **not** store fact rows.
- QuantDinger market/fundamental APIs are **ingestion origins**, not research query sources.
- Qlib binary cache is **derived**, never the only data source.
- D1 never stores bulk OHLCV / PIT / Level2 detail.
- R2 never becomes a permanent Level2 raw archive.

## Reuse of existing QuantDinger pieces

| Existing asset | Continues to own | Research interaction |
| --- | --- | --- |
| `qd_market_symbols` (PG) | Trading instrument catalog | Thin sync → D1 `instrument_ref` |
| `qd_universes` / `qd_universe_members` (PG) | Business / live universe editing | Export immutable snapshots → R2; research reads snapshots only |
| `qd_fundamental_snapshots` (PG) | Trading / strategy PIT for ops | Optional seed for ingest; research PIT SSOT is R2 after materialization |
| `workers/l2-factors-d1` + `l2_factors` | Hot Level2 factors | Unchanged; not migrated into `qd_research` |
| `l2/` + Baidu paths | Level2 detail storage | Unchanged; see [LEVEL2_INGEST_CN.md](../LEVEL2_INGEST_CN.md) |
| QuantDinger market data APIs | Live/ops bars | Ingest → R2 Canonical; research via `DataQuery` |

## Hard research read path

```text
DataQuery
   → Canonical Repository
   → R2 Canonical / Local Cache
   → DuckDB (ad-hoc) or Qlib Materializer (derived cache)
```

Forbidden for research backtests:

- Calling QuantDinger market APIs as the query source
- Reading current PG universe membership instead of a universe snapshot
- Reading Qlib cache without going through Canonical + Materializer
- Using `publish_time` alone for PIT (must use `available_time <= knowledge_time`)

## Acceptance criteria (document-level)

Phase 1 design is accepted when implementers can build from these docs without inventing parallel schemas, and when future CI can encode:

| Check | Requirement |
| --- | --- |
| OHLCV | Same Canonical snapshot yields byte/value-stable bars across DuckDB reads |
| PIT | Random sample: `available_time <= knowledge_time` selection matches Contract |
| Universe | Historical membership from R2 snapshot equals Dataset binding; independent of live PG edits |
| Feature | Offline feature values reproducible under fixed `dataset_hash` |
| Leakage | Any `available_time > knowledge_time` access fails |
| Scope | Research backtest need **not** match production PnL yet |

## Explicit non-goals (still)

- Implementing Qlib Adapter / Materializer
- Migrating PG universe/fundamental tables into D1
- Kafka / Flink / Spark / K8s
- Frontend changes
- Changing existing Level2 Baidu/R2 convert/upload behavior
- Full Feature DSL compiler / pre-post adjustment engine

## Next phase

1. Deploy `qd_research` D1 + wire production `D1_RESEARCH_*`
2. Ingest market/PIT Canonical from QuantDinger Source → R2
3. Feature DSL offline/online consistency tests
4. Qlib Materializer (derived cache only)
5. Differential research vs production backtest (later phase)
