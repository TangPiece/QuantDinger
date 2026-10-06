-- Phase 6I：Paper / Shadow E2E（大 payload 在 R2）

CREATE TABLE IF NOT EXISTS e2e_scenario_run (
  scenario_run_id     TEXT NOT NULL PRIMARY KEY,
  scenario_id         TEXT NOT NULL DEFAULT '',
  run_id              TEXT NOT NULL DEFAULT '',
  session_id          TEXT NOT NULL DEFAULT '',
  mode                TEXT NOT NULL DEFAULT 'PAPER',
  status              TEXT NOT NULL DEFAULT 'OK',
  trace_id            TEXT NOT NULL DEFAULT '',
  dataset_hash        TEXT NOT NULL DEFAULT '',
  strategy_version    TEXT NOT NULL DEFAULT '',
  strategy_id         TEXT NOT NULL DEFAULT '',
  intent_fingerprint  TEXT NOT NULL DEFAULT '',
  engine_version      TEXT NOT NULL DEFAULT 'qd_e2e@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_e2e_scenario_session
  ON e2e_scenario_run (session_id);
CREATE INDEX IF NOT EXISTS idx_e2e_scenario_run
  ON e2e_scenario_run (run_id);

CREATE TABLE IF NOT EXISTS e2e_session (
  session_id          TEXT NOT NULL PRIMARY KEY,
  trading_date        TEXT NOT NULL DEFAULT '',
  market              TEXT NOT NULL DEFAULT '',
  mode                TEXT NOT NULL DEFAULT 'PAPER',
  status              TEXT NOT NULL DEFAULT 'OPEN',
  account_id          TEXT NOT NULL DEFAULT '',
  portfolio_id        TEXT NOT NULL DEFAULT '',
  dataset_hash        TEXT NOT NULL DEFAULT '',
  strategy_version    TEXT NOT NULL DEFAULT '',
  strategy_id         TEXT NOT NULL DEFAULT '',
  opened_at           TEXT,
  closed_at           TEXT,
  engine_version      TEXT NOT NULL DEFAULT 'qd_e2e@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_e2e_session_date
  ON e2e_session (trading_date);

CREATE TABLE IF NOT EXISTS e2e_consistency_score (
  score_id                TEXT NOT NULL PRIMARY KEY,
  run_id                  TEXT NOT NULL DEFAULT '',
  session_id              TEXT NOT NULL DEFAULT '',
  signal_consistency      REAL NOT NULL DEFAULT 0,
  order_consistency       REAL NOT NULL DEFAULT 0,
  execution_consistency   REAL NOT NULL DEFAULT 0,
  position_consistency    REAL NOT NULL DEFAULT 0,
  reconciliation_score    REAL NOT NULL DEFAULT 0,
  audit_coverage          REAL NOT NULL DEFAULT 0,
  safety_coverage         REAL NOT NULL DEFAULT 0,
  overall                 REAL NOT NULL DEFAULT 0,
  engine_version          TEXT NOT NULL DEFAULT 'qd_e2e@1',
  metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS e2e_virtual_order (
  virtual_order_id    TEXT NOT NULL PRIMARY KEY,
  session_id          TEXT NOT NULL DEFAULT '',
  scenario_run_id     TEXT NOT NULL DEFAULT '',
  trace_id            TEXT NOT NULL DEFAULT '',
  instrument_key      TEXT NOT NULL DEFAULT '',
  side                TEXT NOT NULL DEFAULT 'BUY',
  quantity            REAL NOT NULL DEFAULT 0,
  status              TEXT NOT NULL DEFAULT 'WOULD_SUBMIT',
  created_at          TEXT,
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_e2e_virtual_session
  ON e2e_virtual_order (session_id);
