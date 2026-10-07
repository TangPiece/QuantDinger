-- Phase 7A：Live Read-only（snapshot 大 payload 在 R2）

CREATE TABLE IF NOT EXISTS live_readonly_session (
  session_id          TEXT NOT NULL PRIMARY KEY,
  environment         TEXT NOT NULL DEFAULT 'LIVE_READONLY',
  account_id          TEXT NOT NULL DEFAULT '',
  portfolio_id        TEXT NOT NULL DEFAULT '',
  trading_date        TEXT NOT NULL DEFAULT '',
  dataset_hash        TEXT NOT NULL DEFAULT '',
  model_version       TEXT NOT NULL DEFAULT '',
  strategy_version    TEXT NOT NULL DEFAULT '',
  status              TEXT NOT NULL DEFAULT 'OPEN',
  engine_version      TEXT NOT NULL DEFAULT 'qd_live_readonly@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS live_readonly_snapshot_index (
  snapshot_id         TEXT NOT NULL PRIMARY KEY,
  session_id          TEXT NOT NULL DEFAULT '',
  account_id          TEXT NOT NULL DEFAULT '',
  captured_at         TEXT NOT NULL DEFAULT '',
  storage_uri         TEXT NOT NULL DEFAULT '',
  engine_version      TEXT NOT NULL DEFAULT 'qd_live_readonly@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_live_readonly_snapshot_session
  ON live_readonly_snapshot_index (session_id);

CREATE TABLE IF NOT EXISTS trading_environment_state (
  account_id          TEXT NOT NULL PRIMARY KEY,
  environment         TEXT NOT NULL DEFAULT 'PAPER',
  updated_at          TEXT NOT NULL DEFAULT '',
  engine_version      TEXT NOT NULL DEFAULT 'qd_live_readonly@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);
