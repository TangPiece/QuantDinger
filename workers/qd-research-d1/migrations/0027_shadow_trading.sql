-- Phase 7B：Shadow Trading + Live MD session 索引（大 payload 在 R2）

CREATE TABLE IF NOT EXISTS live_md_session (
  session_id          TEXT NOT NULL PRIMARY KEY,
  feed_id             TEXT NOT NULL DEFAULT 'default',
  account_id          TEXT NOT NULL DEFAULT '',
  dataset_hash        TEXT NOT NULL DEFAULT '',
  model_version       TEXT NOT NULL DEFAULT '',
  strategy_version    TEXT NOT NULL DEFAULT '',
  status              TEXT NOT NULL DEFAULT 'OPEN',
  engine_version      TEXT NOT NULL DEFAULT 'qd_live_md@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS shadow_session (
  session_id          TEXT NOT NULL PRIMARY KEY,
  account_id          TEXT NOT NULL DEFAULT '',
  environment         TEXT NOT NULL DEFAULT 'SHADOW',
  dataset_hash        TEXT NOT NULL DEFAULT '',
  model_version       TEXT NOT NULL DEFAULT '',
  strategy_version    TEXT NOT NULL DEFAULT '',
  status              TEXT NOT NULL DEFAULT 'OPEN',
  engine_version      TEXT NOT NULL DEFAULT 'qd_shadow@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS shadow_order_index (
  order_id            TEXT NOT NULL PRIMARY KEY,
  session_id          TEXT NOT NULL DEFAULT '',
  client_order_id     TEXT NOT NULL DEFAULT '',
  symbol              TEXT NOT NULL DEFAULT '',
  side                TEXT NOT NULL DEFAULT '',
  status              TEXT NOT NULL DEFAULT '',
  engine_version      TEXT NOT NULL DEFAULT 'qd_shadow@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_shadow_order_session
  ON shadow_order_index (session_id);

CREATE TABLE IF NOT EXISTS shadow_execution_index (
  execution_id        TEXT NOT NULL PRIMARY KEY,
  order_id            TEXT NOT NULL DEFAULT '',
  session_id          TEXT NOT NULL DEFAULT '',
  symbol              TEXT NOT NULL DEFAULT '',
  quantity            REAL NOT NULL DEFAULT 0,
  price               REAL NOT NULL DEFAULT 0,
  engine_version      TEXT NOT NULL DEFAULT 'qd_shadow@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_shadow_execution_order
  ON shadow_execution_index (order_id);

CREATE TABLE IF NOT EXISTS shadow_compare_run (
  run_id              TEXT NOT NULL PRIMARY KEY,
  account_id          TEXT NOT NULL DEFAULT '',
  storage_uri         TEXT NOT NULL DEFAULT '',
  engine_version      TEXT NOT NULL DEFAULT 'qd_shadow@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);
