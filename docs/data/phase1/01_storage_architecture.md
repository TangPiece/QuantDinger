# 01 — Storage Architecture

## Goal

Lock the logical data layers and their physical backends so research, trading, and Level2 never share a single ambiguous “DataLake” path.

## Logical layers

```text
Source
  → Staging (ephemeral)
  → Canonical (research fact SSOT on R2)
  → Factor / Dataset / Snapshot / Artifact
  → Local Cache / DuckDB
  → Qlib Materializer → Qlib Cache (derived)
```

| Logical layer | Meaning | Physical home |
| --- | --- | --- |
| Source | Vendor / platform origin | QuantDinger market & fundamental APIs; Baidu Level2 raw |
| Staging | Temporary normalize/validate workspace | Local disk only; delete after successful publish |
| Canonical | Immutable research fact data | **R2 `qd/canonical/`** (+ local hot cache) |
| Factor | Computed research factor assets | **R2 `qd/factor/`** |
| Hot L2 factors | Online chart/query store | **D1 `l2_factors`** (existing) |
| Registry | Definitions, versions, jobs | **D1 `qd_research`** |
| Ops metadata | Live trading catalog/universe | **PostgreSQL** |
| Derived cache | Engine-specific materialization | Local `qlib-cache/{dataset_hash}/` |

## End-to-end flow

```text
QuantDinger Source                 Baidu Level2 Raw
 (Ingestion Origin)                       |
        |                                 v
        v                          Local Processor
     Ingestion                            |
   (staging temp)                   +-----+-----+
        |                           v           v
        v                     D1 l2_factors   R2 qd/factor/
R2 qd/canonical/                  (hot)      (+ normalized L2 if needed)
  market / pit / universe_snapshot /
  corporate_action / trading_status
        |
   +----+----+
   v         v
Local     DuckDB
 Cache   Research Query
   |
   v (reserved)
Qlib Materializer -> local qlib-cache/{dataset_hash}/

D1 qd_research  = Registry / Version / Snapshot / Experiment index
PostgreSQL      = Trading Operational SSOT
```

## Role of QuantDinger Source

QuantDinger market and fundamental APIs are:

```text
Source / Ingestion Origin
```

They are **not** the research query source.

After a dataset enters the research system:

```text
QuantDinger Source
      → Ingestion
      → R2 Canonical Dataset
      → DuckDB / Qlib (via DataQuery)
```

If ingest is incomplete, research must fail closed (missing Canonical), not silently fall back to live API bars.

## Role of Baidu Netdisk

Baidu is the **Level2 Raw Archive SSOT** (~5TB). Do not re-archive raw Level2 permanently on R2.

Processor may:

1. Download a day to local staging
2. Compute features
3. Write hot rows to D1 `l2_factors`
4. Write research factor parquet to R2 `qd/factor/`
5. Delete local detail

## Role of R2

R2 is the **Research Data SSOT** for:

- Canonical market / PIT / universe snapshots / corporate actions / trading status
- Research factor assets
- Dataset / snapshot manifests
- Artifacts (models, reports, predictions)

R2 is **not**:

- Level2 raw archive
- Trading OLTP database
- Qlib binary long-term store (Phase 1: Qlib cache stays local)

## Role of Local SSD

```text
~/.quantdinger/cache/canonical/...
~/.quantdinger/cache/factor/...
~/.quantdinger/cache/qlib-cache/{dataset_hash}/...
```

Caches are disposable. Corruption or wipe must be fixable by re-fetch from R2 / re-materialize.

## Role of DuckDB

DuckDB is the **research query engine** over Parquet (local cache or signed/local paths). It is not a durable system of record.

## Role of Qlib cache

```text
Canonical (R2)
  → Materializer
  → local qlib-cache/{dataset_hash}/
```

Qlib bins are derived. `DataQuery` must never depend on them.

## Level2 factor dual path

```text
Level2 Raw (Baidu)
  → Processor
  → L2 Feature
       ├─ D1 l2_factors     Hot / Online Factor Store
       └─ R2 qd/factor/     Long-term Research Factor Asset
```

- Charts / online panels read **D1 `l2_factors`** (existing Worker).
- Factor Lab / research datasets read **R2 factor assets** through `DataQuery.feature()` / Factor Registry.
- Registry may record `backend=d1_l2_factors` or `backend=r2_factor` without merging physical stores.

## Universe dual path

```text
PG qd_universes / qd_universe_members
        │  (business current state)
        ▼ export job
Immutable Universe Snapshot
        ▼
R2 qd/canonical/universe/...
        ▼
data_snapshot (+ items)
        ▼
Dataset binds snapshot_id  → research reproducible
```

Research `DataQuery.universe()` resolves membership from the **snapshot**, not live PG rows.

## Time semantics (locked)

| Field | Meaning |
| --- | --- |
| `event_time` | When the economic event occurred |
| `trading_time` | Trading-session timestamp |
| `publish_time` | When vendor/market published the data |
| `available_time` | When QuantDinger could actually obtain it |
| `knowledge_time` | Information cutoff allowed in a backtest step |
| `execution_time` | When an order actually executed |

Rules:

1. Do not collapse these into a single `timestamp`.
2. `publish_time` and `available_time` may differ (late feed, batch import, timezone cutoffs).
3. PIT selection uses **only**:

```text
available_time <= knowledge_time
```

then latest `available_time`, with deterministic tie-break (`revision` DESC, `record_id` DESC).

4. Normal daily research derives `knowledge_time` from `trading_date` + execution rule (e.g. session close), not free-form user clocks.

## Data version vs snapshot

| Concept | Answers | Stored |
| --- | --- | --- |
| `data_version` | What logical version is this dataset slice? | D1 `qd_research.data_version` |
| `data_snapshot` | Exactly which files/checksums did an experiment use? | D1 snapshot tables + R2 `qd/snapshot/{id}/manifest.json` |

A Dataset version may compose multiple data versions (market + PIT + universe). The Snapshot pins the concrete file set.

## Forbidden shortcuts

| Shortcut | Why forbidden |
| --- | --- |
| Research reads live QuantDinger API bars | Non-reproducible; source drift |
| Research reads live PG universe | Survivorship / edit drift |
| Persist permanent `raw/` on R2 for stocks/L2 | Duplicates existing origins |
| Store bulk facts in D1 | Size / type / cost wrong tool |
| Treat Qlib bin as Canonical | Engine lock-in |

## Related docs

- [03_r2_layout.md](03_r2_layout.md) — concrete prefixes
- [05_contracts.md](05_contracts.md) — `DataQuery` surface
- [06_research_consistency.md](06_research_consistency.md) — consistency tests
