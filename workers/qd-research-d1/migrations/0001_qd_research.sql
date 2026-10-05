-- qd_research — Research registry (metadata only; no bulk market/PIT facts)
-- Source: docs/data/phase1/02_d1_research_schema.md

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
