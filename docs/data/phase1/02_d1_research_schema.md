# 02 — D1 `qd_research` Schema

## Scope

New Cloudflare D1 database **`qd_research`**, separate from existing **`l2_factors`**.

| Database | Purpose | Worker (future) |
| --- | --- | --- |
| `l2_factors` | Hot Level2 factor rows | `workers/l2-factors-d1` (exists) |
| `qd_research` | Research registry / versions / experiments | `workers/qd-research-d1` (doc-only; not created in Phase 1) |

Env (future):

```text
D1_RESEARCH_WORKER_URL=...
D1_RESEARCH_WORKER_TOKEN=...
```

Do **not** overload `D1_WORKER_URL` used by Level2 factors.

## Type rules

> D1 uses SQLite native types: **TEXT / INTEGER / REAL / BLOB**.
> JSON fields are stored as **TEXT**, validated by `schema_version` + application-level validation.
> Timestamps are ISO-8601 TEXT (UTC preferred). IDs/UUIDs are TEXT.

### JSON size policy

| Kind | Store in |
| --- | --- |
| Small metadata, short definitions, metrics summaries | D1 TEXT JSON |
| Large dataset manifests, full model configs, reports, prediction frames | **R2**; D1 keeps `storage_uri` / checksum / size |

Guideline: prefer keeping D1 JSON under ~32 KiB per row. Larger blobs must go to R2 artifacts.

## DDL (migration `0001_qd_research.sql`)

```sql
-- =============================================================================
-- qd_research — Research registry (metadata only; no bulk market/PIT facts)
-- =============================================================================

CREATE TABLE IF NOT EXISTS data_source (
  source_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  provider_type    TEXT,
  version          TEXT,
  metadata_json    TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_version (
  data_version_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_code     TEXT NOT NULL,
  version          TEXT NOT NULL,
  source_id        INTEGER REFERENCES data_source(source_id),
  schema_version   TEXT NOT NULL,
  status           TEXT NOT NULL,
  row_count        INTEGER,
  min_time         TEXT,
  max_time         TEXT,
  checksum         TEXT,
  r2_uri           TEXT,
  metadata_json    TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL,
  UNIQUE (dataset_code, version)
);

CREATE INDEX IF NOT EXISTS idx_data_version_status
  ON data_version (dataset_code, status);

CREATE TABLE IF NOT EXISTS data_snapshot (
  snapshot_id      TEXT PRIMARY KEY,
  name             TEXT,
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS data_snapshot_item (
  snapshot_id      TEXT NOT NULL REFERENCES data_snapshot(snapshot_id),
  data_version_id  INTEGER NOT NULL REFERENCES data_version(data_version_id),
  path             TEXT NOT NULL,
  checksum         TEXT,
  PRIMARY KEY (snapshot_id, data_version_id)
);

CREATE TABLE IF NOT EXISTS dataset (
  dataset_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT NOT NULL,
  version          TEXT NOT NULL,
  name             TEXT NOT NULL,
  frequency        TEXT NOT NULL,
  universe_code    TEXT,
  universe_version TEXT,
  snapshot_id      TEXT REFERENCES data_snapshot(snapshot_id),
  schema_version   TEXT NOT NULL,
  -- Small definition or pointer: {"definition_uri":"r2://...","digest":"..."}
  definition_json  TEXT NOT NULL,
  price_policy_json TEXT NOT NULL DEFAULT '{}',
  status           TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at       TEXT NOT NULL,
  UNIQUE (code, version)
);

CREATE INDEX IF NOT EXISTS idx_dataset_snapshot
  ON dataset (snapshot_id);

CREATE TABLE IF NOT EXISTS feature (
  feature_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT NOT NULL,
  version          TEXT NOT NULL,
  name             TEXT NOT NULL,
  expression       TEXT NOT NULL,
  frequency        TEXT NOT NULL,
  definition_json  TEXT NOT NULL,
  -- Physical backend hint: r2_factor | d1_l2_factors | computed
  backend          TEXT NOT NULL DEFAULT 'r2_factor',
  online_supported INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at       TEXT NOT NULL,
  UNIQUE (code, version)
);

CREATE TABLE IF NOT EXISTS feature_dependency (
  feature_id       INTEGER NOT NULL REFERENCES feature(feature_id),
  dependency_type  TEXT NOT NULL,
  dependency_code  TEXT NOT NULL,
  PRIMARY KEY (feature_id, dependency_type, dependency_code)
);

CREATE TABLE IF NOT EXISTS label (
  label_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT NOT NULL,
  version          TEXT NOT NULL,
  name             TEXT NOT NULL,
  expression       TEXT NOT NULL,
  horizon          INTEGER,
  definition_json  TEXT NOT NULL,
  created_at       TEXT NOT NULL,
  UNIQUE (code, version)
);

CREATE TABLE IF NOT EXISTS processor (
  processor_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT NOT NULL,
  version          TEXT NOT NULL,
  definition_json  TEXT NOT NULL,
  created_at       TEXT NOT NULL,
  UNIQUE (code, version)
);

CREATE TABLE IF NOT EXISTS model (
  model_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  engine           TEXT NOT NULL,
  created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_version (
  model_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_id         INTEGER NOT NULL REFERENCES model(model_id),
  version          TEXT NOT NULL,
  dataset_id       INTEGER REFERENCES dataset(dataset_id),
  processor_id     INTEGER REFERENCES processor(processor_id),
  config_json      TEXT NOT NULL,
  artifact_id      TEXT,
  metrics_json     TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL,
  UNIQUE (model_id, version)
);

CREATE TABLE IF NOT EXISTS artifact (
  artifact_id      TEXT PRIMARY KEY,
  artifact_type    TEXT NOT NULL,
  storage_uri      TEXT NOT NULL,
  checksum         TEXT,
  size_bytes       INTEGER,
  metadata_json    TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment (
  experiment_id    TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  dataset_id       INTEGER REFERENCES dataset(dataset_id),
  model_version_id INTEGER REFERENCES model_version(model_version_id),
  snapshot_id      TEXT REFERENCES data_snapshot(snapshot_id),
  dataset_hash     TEXT,
  status           TEXT NOT NULL,
  mlflow_run_id    TEXT,
  parameters_json  TEXT NOT NULL DEFAULT '{}',
  metrics_json     TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL,
  started_at       TEXT,
  finished_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_experiment_hash
  ON experiment (dataset_hash);

CREATE TABLE IF NOT EXISTS job (
  job_id           TEXT PRIMARY KEY,
  job_type         TEXT NOT NULL,
  status           TEXT NOT NULL,
  payload_json     TEXT NOT NULL DEFAULT '{}',
  result_json      TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL,
  started_at       TEXT,
  finished_at      TEXT
);

-- Thin catalog bridges (not full PG copies; no fact data)
CREATE TABLE IF NOT EXISTS instrument_ref (
  instrument_key   TEXT PRIMARY KEY,
  market           TEXT NOT NULL,
  symbol           TEXT NOT NULL,
  exchange         TEXT,
  pg_symbol_id     INTEGER,
  lot_size         INTEGER NOT NULL DEFAULT 1,
  tick_size        REAL,
  status           TEXT NOT NULL DEFAULT 'ACTIVE',
  synced_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_instrument_ref_market_symbol
  ON instrument_ref (market, symbol);

CREATE TABLE IF NOT EXISTS universe_ref (
  universe_code    TEXT PRIMARY KEY,
  pg_universe_id   INTEGER,
  market           TEXT,
  synced_at        TEXT NOT NULL
);
```

## Semantics notes

### `instrument_ref`

Synced from PostgreSQL `qd_market_symbols` for research binding keys (`instrument_key`).
Does **not** store OHLCV.

Suggested `instrument_key` format (Contract):

```text
{market}:{symbol}
```

Examples: `CNStock:000001`, `HKStock:00700`, `USStock:AAPL`.

### `universe_ref`

Points at PG business universe identity. **Research membership must not be resolved from this table alone.**
Membership for research comes from R2 universe snapshots referenced by `dataset.universe_version` + `snapshot_id`.

### `dataset.definition_json`

Either:

```json
{
  "inline": { "features": ["close"], "label": {"code": "fwd_ret_5d@1.0.0"} }
}
```

or pointer form when large:

```json
{
  "definition_uri": "r2://quantdinger-data/qd/dataset/CSI300_DAILY/3.0.0/def.json",
  "digest": "sha256:..."
}
```

### `feature.backend`

| Value | Meaning |
| --- | --- |
| `r2_factor` | Values in R2 `qd/factor/` |
| `d1_l2_factors` | Hot Level2 columns in existing `l2_factors` |
| `computed` | Evaluated from expression against Canonical at query time |

## Example inserts

```sql
INSERT INTO data_source (code, name, provider_type, version, metadata_json, created_at)
VALUES ('quantdinger_source', 'QuantDinger Market Source', 'platform', '1', '{}', '2026-10-05T00:00:00Z');

INSERT INTO data_snapshot (snapshot_id, name, created_at, metadata_json)
VALUES ('snap_20261005_csi300', 'CSI300 research pack 2026-10-05', '2026-10-05T12:00:00Z', '{}');

INSERT INTO dataset (
  code, version, name, frequency, universe_code, universe_version,
  snapshot_id, schema_version, definition_json, price_policy_json, status, created_at
) VALUES (
  'CSI300_DAILY', '3.0.0', 'CSI300 Daily', '1d', 'CSI300', '2026.10.05',
  'snap_20261005_csi300', 'market_bar_daily@1',
  '{"definition_uri":"r2://quantdinger-data/qd/dataset/CSI300_DAILY/3.0.0/def.json","digest":"sha256:demo"}',
  '{"adjustment":"post"}',
  'ACTIVE', '2026-10-05T12:00:00Z'
);
```

## Out of scope for this database

Do **not** create tables for:

- `market_bar`, `pit_fundamental` fact rows
- Level2 ticks
- Wide daily factor fact tables (those live on R2; hot L2 stays in `l2_factors`)

## Relation to PostgreSQL

| Concern | System |
| --- | --- |
| Live trading symbols / lot size ops | PG `qd_market_symbols` |
| Editable strategy universes | PG `qd_universes` / members |
| Trading PIT fundamentals for Strategy V2 | PG `qd_fundamental_snapshots` |
| Research experiment binding | D1 `qd_research` + R2 snapshots |

No table-for-table migration of PG → D1 in Phase 1.
