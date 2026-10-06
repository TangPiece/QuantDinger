-- Phase 6A：Production Runtime Registry（明细在 R2）

CREATE TABLE IF NOT EXISTS production_runtime (
  runtime_id       TEXT NOT NULL PRIMARY KEY,
  bundle_hash      TEXT NOT NULL,
  strategy_code    TEXT NOT NULL DEFAULT '',
  market           TEXT NOT NULL DEFAULT 'CN_A',
  environment      TEXT NOT NULL DEFAULT 'PAPER',
  status           TEXT NOT NULL DEFAULT 'STARTING',
  session_phase    TEXT NOT NULL DEFAULT 'PRE_MARKET',
  trading_date     TEXT NOT NULL DEFAULT '',
  started_at       TEXT,
  last_heartbeat   TEXT,
  engine_version   TEXT NOT NULL DEFAULT 'qd_production_runtime@1',
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_prt_bundle
  ON production_runtime (bundle_hash);

CREATE INDEX IF NOT EXISTS idx_prt_code
  ON production_runtime (strategy_code);

CREATE INDEX IF NOT EXISTS idx_prt_status
  ON production_runtime (status);

CREATE TABLE IF NOT EXISTS production_runtime_event (
  event_id       TEXT NOT NULL PRIMARY KEY,
  runtime_id     TEXT NOT NULL,
  event_type     TEXT NOT NULL,
  trading_date   TEXT NOT NULL DEFAULT '',
  session_phase  TEXT NOT NULL DEFAULT '',
  message        TEXT NOT NULL DEFAULT '',
  payload_json   TEXT NOT NULL DEFAULT '{}',
  created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pre_runtime
  ON production_runtime_event (runtime_id);

CREATE INDEX IF NOT EXISTS idx_pre_date
  ON production_runtime_event (trading_date);

CREATE INDEX IF NOT EXISTS idx_pre_type
  ON production_runtime_event (event_type);

CREATE TABLE IF NOT EXISTS production_runtime_run (
  run_id           TEXT NOT NULL PRIMARY KEY,
  runtime_id       TEXT NOT NULL,
  bundle_hash      TEXT NOT NULL,
  idempotency_key  TEXT NOT NULL UNIQUE,
  trading_date     TEXT NOT NULL DEFAULT '',
  session_phase    TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'OK',
  n_signals        INTEGER NOT NULL DEFAULT 0,
  n_intents        INTEGER NOT NULL DEFAULT 0,
  bridge_run_id    TEXT NOT NULL DEFAULT '',
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_prr_runtime
  ON production_runtime_run (runtime_id);

CREATE INDEX IF NOT EXISTS idx_prr_bundle
  ON production_runtime_run (bundle_hash);
