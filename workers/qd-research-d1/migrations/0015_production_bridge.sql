-- Phase 5F：Research → Production Bridge Registry（明细在 R2）

CREATE TABLE IF NOT EXISTS production_bundle (
  bundle_hash             TEXT NOT NULL PRIMARY KEY,
  strategy_hash           TEXT NOT NULL,
  strategy_code           TEXT NOT NULL DEFAULT '',
  cv_hash                 TEXT NOT NULL DEFAULT '',
  backtest_hash           TEXT NOT NULL DEFAULT '',
  qlib_run_hash           TEXT NOT NULL DEFAULT '',
  dataset_hash            TEXT NOT NULL DEFAULT '',
  materialization_id      TEXT NOT NULL DEFAULT '',
  model_artifact_id       TEXT NOT NULL DEFAULT '',
  model_version           TEXT NOT NULL DEFAULT '',
  processor_hash          TEXT NOT NULL DEFAULT '',
  processor_artifact_uri  TEXT NOT NULL DEFAULT '',
  pipeline_digest         TEXT NOT NULL DEFAULT '',
  universe_code           TEXT NOT NULL DEFAULT '',
  snapshot_id             TEXT NOT NULL DEFAULT '',
  execution_policy        TEXT NOT NULL DEFAULT 'NEXT_OPEN',
  realism                 TEXT NOT NULL DEFAULT 'GROSS',
  market_rule             TEXT NOT NULL DEFAULT '',
  status                  TEXT NOT NULL DEFAULT 'DRAFT',
  parent_bundle_hash      TEXT NOT NULL DEFAULT '',
  dependency_lock_json    TEXT NOT NULL DEFAULT '{}',
  feature_hashes_json     TEXT NOT NULL DEFAULT '[]',
  engine_version          TEXT NOT NULL DEFAULT 'qd_production_bridge@1',
  storage_uri             TEXT NOT NULL DEFAULT '',
  checksum                TEXT,
  created_at              TEXT NOT NULL,
  metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pb_strategy
  ON production_bundle (strategy_hash);

CREATE INDEX IF NOT EXISTS idx_pb_code
  ON production_bundle (strategy_code);

CREATE INDEX IF NOT EXISTS idx_pb_status
  ON production_bundle (status);

CREATE INDEX IF NOT EXISTS idx_pb_cv
  ON production_bundle (cv_hash);

CREATE TABLE IF NOT EXISTS production_deployment (
  deployment_id         TEXT NOT NULL PRIMARY KEY,
  bundle_hash           TEXT NOT NULL,
  strategy_code         TEXT NOT NULL,
  status                TEXT NOT NULL DEFAULT 'DEPLOYED',
  previous_bundle_hash  TEXT NOT NULL DEFAULT '',
  deployed_at           TEXT,
  created_at            TEXT NOT NULL,
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pd_code
  ON production_deployment (strategy_code);

CREATE INDEX IF NOT EXISTS idx_pd_bundle
  ON production_deployment (bundle_hash);

CREATE INDEX IF NOT EXISTS idx_pd_status
  ON production_deployment (status);

CREATE TABLE IF NOT EXISTS production_deployment_run (
  run_id          TEXT NOT NULL PRIMARY KEY,
  bundle_hash     TEXT NOT NULL,
  deployment_id   TEXT NOT NULL DEFAULT '',
  trading_date    TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'OK',
  n_signals       INTEGER NOT NULL DEFAULT 0,
  n_intents       INTEGER NOT NULL DEFAULT 0,
  gate_json       TEXT NOT NULL DEFAULT '{}',
  storage_uri     TEXT NOT NULL DEFAULT '',
  created_at      TEXT NOT NULL,
  metadata_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pdr_bundle
  ON production_deployment_run (bundle_hash);

CREATE INDEX IF NOT EXISTS idx_pdr_date
  ON production_deployment_run (trading_date);
