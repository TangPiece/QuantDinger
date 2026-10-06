-- Phase 6B：Portfolio / Position Service Registry（明细在 R2）

CREATE TABLE IF NOT EXISTS production_account (
  account_id       TEXT NOT NULL PRIMARY KEY,
  environment      TEXT NOT NULL DEFAULT 'PAPER',
  market           TEXT NOT NULL DEFAULT 'CN_A',
  status           TEXT NOT NULL DEFAULT 'ACTIVE',
  currency         TEXT NOT NULL DEFAULT 'CNY',
  available_cash   REAL NOT NULL DEFAULT 0,
  frozen_cash      REAL NOT NULL DEFAULT 0,
  market_value     REAL NOT NULL DEFAULT 0,
  equity           REAL NOT NULL DEFAULT 0,
  realized_pnl     REAL NOT NULL DEFAULT 0,
  unrealized_pnl   REAL NOT NULL DEFAULT 0,
  total_pnl        REAL NOT NULL DEFAULT 0,
  engine_version   TEXT NOT NULL DEFAULT 'qd_portfolio_service@1',
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pac_env
  ON production_account (environment);

CREATE INDEX IF NOT EXISTS idx_pac_status
  ON production_account (status);

CREATE TABLE IF NOT EXISTS production_portfolio (
  portfolio_id     TEXT NOT NULL PRIMARY KEY,
  account_id       TEXT NOT NULL,
  runtime_id       TEXT NOT NULL DEFAULT '',
  bundle_hash      TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'ACTIVE',
  trading_date     TEXT NOT NULL DEFAULT '',
  engine_version   TEXT NOT NULL DEFAULT 'qd_portfolio_service@1',
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ppf_account
  ON production_portfolio (account_id);

CREATE INDEX IF NOT EXISTS idx_ppf_runtime
  ON production_portfolio (runtime_id);

CREATE TABLE IF NOT EXISTS production_position (
  portfolio_id         TEXT NOT NULL,
  instrument_key       TEXT NOT NULL,
  quantity             REAL NOT NULL DEFAULT 0,
  available_quantity   REAL NOT NULL DEFAULT 0,
  frozen_quantity      REAL NOT NULL DEFAULT 0,
  avg_cost             REAL NOT NULL DEFAULT 0,
  market_value         REAL NOT NULL DEFAULT 0,
  currency             TEXT NOT NULL DEFAULT 'CNY',
  as_of                TEXT,
  metadata_json        TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (portfolio_id, instrument_key)
);

CREATE INDEX IF NOT EXISTS idx_ppo_portfolio
  ON production_position (portfolio_id);

CREATE TABLE IF NOT EXISTS production_position_event (
  event_id         TEXT NOT NULL PRIMARY KEY,
  portfolio_id     TEXT NOT NULL,
  account_id       TEXT NOT NULL DEFAULT '',
  event_type       TEXT NOT NULL,
  instrument_key   TEXT NOT NULL DEFAULT '',
  trading_date     TEXT NOT NULL DEFAULT '',
  quantity         REAL NOT NULL DEFAULT 0,
  price            REAL NOT NULL DEFAULT 0,
  cash_delta       REAL NOT NULL DEFAULT 0,
  fee              REAL NOT NULL DEFAULT 0,
  idempotency_key  TEXT NOT NULL DEFAULT '',
  message          TEXT NOT NULL DEFAULT '',
  payload_json     TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ppe_portfolio
  ON production_position_event (portfolio_id);

CREATE INDEX IF NOT EXISTS idx_ppe_date
  ON production_position_event (trading_date);

CREATE INDEX IF NOT EXISTS idx_ppe_type
  ON production_position_event (event_type);

CREATE TABLE IF NOT EXISTS production_portfolio_snapshot (
  snapshot_id      TEXT NOT NULL PRIMARY KEY,
  account_id       TEXT NOT NULL,
  portfolio_id     TEXT NOT NULL,
  trading_date     TEXT NOT NULL DEFAULT '',
  knowledge_time   TEXT,
  cash             REAL NOT NULL DEFAULT 0,
  market_value     REAL NOT NULL DEFAULT 0,
  equity           REAL NOT NULL DEFAULT 0,
  realized_pnl     REAL NOT NULL DEFAULT 0,
  unrealized_pnl   REAL NOT NULL DEFAULT 0,
  total_pnl        REAL NOT NULL DEFAULT 0,
  gross_exposure   REAL NOT NULL DEFAULT 0,
  net_exposure     REAL NOT NULL DEFAULT 0,
  runtime_id       TEXT NOT NULL DEFAULT '',
  bundle_hash      TEXT NOT NULL DEFAULT '',
  idempotency_key  TEXT NOT NULL DEFAULT '',
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pps_account
  ON production_portfolio_snapshot (account_id);

CREATE INDEX IF NOT EXISTS idx_pps_portfolio
  ON production_portfolio_snapshot (portfolio_id);

CREATE INDEX IF NOT EXISTS idx_pps_date
  ON production_portfolio_snapshot (trading_date);

CREATE TABLE IF NOT EXISTS production_portfolio_apply (
  apply_id         TEXT NOT NULL PRIMARY KEY,
  account_id       TEXT NOT NULL,
  portfolio_id     TEXT NOT NULL,
  idempotency_key  TEXT NOT NULL UNIQUE,
  trading_date     TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'OK',
  n_deltas         INTEGER NOT NULL DEFAULT 0,
  n_events         INTEGER NOT NULL DEFAULT 0,
  snapshot_id      TEXT NOT NULL DEFAULT '',
  runtime_id       TEXT NOT NULL DEFAULT '',
  run_id           TEXT NOT NULL DEFAULT '',
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ppa_account
  ON production_portfolio_apply (account_id);

CREATE INDEX IF NOT EXISTS idx_ppa_portfolio
  ON production_portfolio_apply (portfolio_id);
