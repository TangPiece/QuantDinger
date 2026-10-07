-- Phase 7D：Controlled Live Production session 扩展 + runtime tick / drift 索引

ALTER TABLE controlled_live_session ADD COLUMN feature_version TEXT NOT NULL DEFAULT '';
ALTER TABLE controlled_live_session ADD COLUMN processor_version TEXT NOT NULL DEFAULT '';
ALTER TABLE controlled_live_session ADD COLUMN snapshot_id TEXT NOT NULL DEFAULT '';
ALTER TABLE controlled_live_session ADD COLUMN stop_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE controlled_live_session ADD COLUMN heartbeat_at TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS controlled_live_runtime_tick (
  tick_id           TEXT NOT NULL PRIMARY KEY,
  session_id        TEXT NOT NULL DEFAULT '',
  account_id        TEXT NOT NULL DEFAULT '',
  storage_uri       TEXT NOT NULL DEFAULT '',
  engine_version    TEXT NOT NULL DEFAULT 'qd_controlled_live@2',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_controlled_live_runtime_tick_session
  ON controlled_live_runtime_tick (session_id);

CREATE INDEX IF NOT EXISTS idx_controlled_live_runtime_tick_account
  ON controlled_live_runtime_tick (account_id);

CREATE TABLE IF NOT EXISTS controlled_live_drift_daily (
  run_id            TEXT NOT NULL PRIMARY KEY,
  account_id        TEXT NOT NULL DEFAULT '',
  trading_date      TEXT NOT NULL DEFAULT '',
  storage_uri       TEXT NOT NULL DEFAULT '',
  engine_version    TEXT NOT NULL DEFAULT 'qd_controlled_live@2',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_controlled_live_drift_daily_account_date
  ON controlled_live_drift_daily (account_id, trading_date);
