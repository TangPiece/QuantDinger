# 03 — R2 Layout

## Goal

Define object-key conventions so Canonical research data, factors, manifests, and artifacts coexist with existing Level2 prefixes without collision.

## Bucket and env

| Variable | Purpose | Example |
| --- | --- | --- |
| `R2_BUCKET` | Shared bucket (or dedicated) | `quantdinger-data` / existing `level2` |
| `R2_PREFIX` | Existing Level2 detail prefix | `l2` |
| `R2_FACTOR_PREFIX` | Legacy Level2 daily wide tables | `l2_factors` |
| `QD_CANONICAL_PREFIX` | New research root | `qd` |

Phase 1 recommendation: keep one bucket; isolate by prefix. Do not rename existing `l2/` keys.

## Existing prefixes (do not change)

```text
l2/{YYYYMMDD}/{code}/{type}.parquet
l2/{YYYY}/{YYYYMM}/{YYYYMMDD}/{code}/{type}.parquet   # Baidu physical nesting via logical-key mapping

l2_factors/{YYYY}/{YYYYMM}/{YYYYMMDD}.parquet         # legacy wide tables; hot query SSOT is D1 l2_factors

l2/_catalog/{backend}/{YYYYMMDD}.parquet
l2/_manifests/{YYYYMMDD}.parquet
```

Logical keys and Baidu hierarchy remain as implemented in
`backend_api_python/app/services/level2_ingest/config.py`.

## New research tree (`qd/`)

```text
qd/
├── canonical/
│   ├── market/
│   │   └── daily/
│   │       └── exchange={CN|HK|US}/
│   │           └── year=YYYY/
│   │               └── month=MM/
│   │                   └── part-*.parquet
│   ├── fundamental/
│   │   └── pit/
│   │       └── exchange={CN|HK|US}/
│   │           └── year=YYYY/
│   │               └── part-*.parquet
│   ├── universe/
│   │   └── code={CSI300}/
│   │       └── version={YYYY.MM.DD|semver}/
│   │           └── part-*.parquet          # REQUIRED for research
│   ├── corporate_action/
│   │   └── exchange={CN|HK|US}/
│   │       └── year=YYYY/
│   │           └── part-*.parquet
│   └── trading_status/
│       └── exchange={CN|HK|US}/
│           └── year=YYYY/
│               └── month=MM/
│                   └── part-*.parquet
│
├── factor/
│   └── daily/
│       └── factor_set={code}@{version}/
│           └── year=YYYY/
│               └── month=MM/
│                   └── part-*.parquet
│
├── dataset/
│   └── {dataset_code}/
│       └── {dataset_version}/
│           ├── def.json
│           └── {snapshot_id}/
│               └── manifest.json
│
├── snapshot/
│   └── {snapshot_id}/
│       └── manifest.json
│
└── artifacts/
    └── {artifact_type}/
        └── {artifact_id}/
            └── ...
```

## Partition rules

1. Prefer `exchange + year (+ month)`. Never one file per instrument for daily bars.
2. Hive-style directory names (`exchange=CN`) for DuckDB `read_parquet` globbing.
3. `part-*.parquet` files should target tens–hundreds of MB compressed, not tiny per-symbol files.
4. Object keys use ASCII; Chinese Level2 type names stay under `l2/` only.

## Universe snapshots (required)

Business universes remain editable in PostgreSQL. Research **must** materialize:

```text
qd/canonical/universe/code={CODE}/version={VERSION}/part-*.parquet
```

Export pipeline:

```text
PG qd_universes / qd_universe_members
  → snapshot job (as_of range or full history intervals)
  → R2 canonical/universe/...
  → register data_version + data_snapshot_item in D1 qd_research
  → Dataset binds universe_code + universe_version + snapshot_id
```

Rules:

- Snapshot rows are immutable; new exports get a new `version`.
- Research `DataQuery.universe()` reads this path (via snapshot), never live PG membership.
- PG `universe_ref` in D1 only identifies codes for UI/sync.

## Factor layout

Stable factor sets (e.g. Alpha158):

```text
qd/factor/daily/factor_set=alpha158@1.0.0/year=2026/month=10/part-000.parquet
```

Wide parquet columns for that set only.

Dynamic / AI factors:

```text
qd/factor/daily/factor_set=rdagent_run_20261005@1/year=2026/month=10/part-000.parquet
```

Prefer **long** schema (`factor_code`, `value`) or a dedicated small set — never grow a single 5000-column mega table.

Level2 hot columns remain in D1 `l2_factors`. Optional research copies may also land under `qd/factor/daily/factor_set=l2_base@1/...` for offline labs.

Phase 4A Factor Dataset Manifest (metadata only; values still under `qd/factor/...`):

```text
qd/dataset/factor/{factor_dataset_id}/manifest.json
```

See [phase4/01_factor_definition.md](../phase4/01_factor_definition.md).

## Manifests

### Snapshot manifest — `qd/snapshot/{snapshot_id}/manifest.json`

```json
{
  "snapshot_id": "snap_20261005_csi300",
  "created_at": "2026-10-05T12:00:00Z",
  "schema_version": "snapshot_manifest@1",
  "items": [
    {
      "dataset_code": "A_STOCK_DAILY",
      "version": "2026.10.05",
      "path": "qd/canonical/market/daily/exchange=CN/year=2026/month=10/part-000.parquet",
      "checksum": "sha256:...",
      "row_count": 123456
    },
    {
      "dataset_code": "CSI300_UNIVERSE",
      "version": "2026.10.05",
      "path": "qd/canonical/universe/code=CSI300/version=2026.10.05/part-000.parquet",
      "checksum": "sha256:..."
    }
  ]
}
```

### Dataset pack — `qd/dataset/{code}/{version}/{snapshot_id}/manifest.json`

Pins the snapshot plus dataset definition digest and `price_policy` used for that experiment pack.

## Local cache mirror

```text
~/.quantdinger/cache/canonical/...   # mirrors qd/canonical/
~/.quantdinger/cache/factor/...      # mirrors qd/factor/
~/.quantdinger/cache/qlib-cache/{dataset_hash}/...
```

Cache keys should preserve relative paths under `qd/` for easy invalidation by checksum.

## What must not appear under `qd/`

| Path | Reason |
| --- | --- |
| `qd/raw/...` permanent | Sources already exist (platform / Baidu) |
| `qd/qlib-bin/...` as SSOT | Local derived cache only in Phase 1 |
| Per-symbol daily trees | Small-file explosion |

## URI convention

Document URIs as:

```text
r2://{bucket}/{key}
```

Example:

```text
r2://quantdinger-data/qd/canonical/market/daily/exchange=CN/year=2026/month=10/part-000.parquet
```

D1 `artifact.storage_uri` and `data_version.r2_uri` use this form.
