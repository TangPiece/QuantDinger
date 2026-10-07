-- Phase 7C：Controlled Live session / order / approval / compare 索引

CREATE TABLE IF NOT EXISTS controlled_live_session (
  session_id            TEXT NOT NULL PRIMARY KEY,
  account_id            TEXT NOT NULL DEFAULT '',
  environment           TEXT NOT NULL DEFAULT 'LIVE_CONTROLLED',
  approved_strategy_id  TEXT NOT NULL DEFAULT '',
  dataset_hash          TEXT NOT NULL DEFAULT '',
  model_version         TEXT NOT NULL DEFAULT '',
  strategy_version      TEXT NOT NULL DEFAULT '',
  status                TEXT NOT NULL DEFAULT 'OPEN',
  order_count           INTEGER NOT NULL DEFAULT 0,
  engine_version        TEXT NOT NULL DEFAULT 'qd_controlled_live@1',
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS controlled_live_order_index (
  order_id              TEXT NOT NULL PRIMARY KEY,
  session_id            TEXT NOT NULL DEFAULT '',
  client_order_id       TEXT NOT NULL UNIQUE,
  broker_order_id       TEXT NOT NULL DEFAULT '',
  symbol                TEXT NOT NULL DEFAULT '',
  side                  TEXT NOT NULL DEFAULT '',
  status                TEXT NOT NULL DEFAULT '',
  engine_version        TEXT NOT NULL DEFAULT 'qd_controlled_live@1',
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_controlled_live_order_session
  ON controlled_live_order_index (session_id);

CREATE TABLE IF NOT EXISTS controlled_live_approval (
  approval_id           TEXT NOT NULL PRIMARY KEY,
  session_id            TEXT NOT NULL DEFAULT '',
  operator_actor        TEXT NOT NULL DEFAULT '',
  approval_token_hash   TEXT NOT NULL DEFAULT '',
  scope                 TEXT NOT NULL DEFAULT 'SINGLE_ORDER',
  status                TEXT NOT NULL DEFAULT 'APPROVED',
  approved_at           TEXT NOT NULL DEFAULT '',
  engine_version        TEXT NOT NULL DEFAULT 'qd_controlled_live@1',
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS controlled_live_compare_run (
  run_id                TEXT NOT NULL PRIMARY KEY,
  account_id            TEXT NOT NULL DEFAULT '',
  storage_uri           TEXT NOT NULL DEFAULT '',
  engine_version        TEXT NOT NULL DEFAULT 'qd_controlled_live@1',
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);
