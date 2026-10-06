-- Phase 6C：Risk Engine Registry（明细在 R2）

CREATE TABLE IF NOT EXISTS risk_policy (
  policy_hash      TEXT NOT NULL PRIMARY KEY,
  policy_code      TEXT NOT NULL,
  policy_version   TEXT NOT NULL,
  engine_version   TEXT NOT NULL DEFAULT 'qd_risk_engine@1',
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}',
  UNIQUE (policy_code, policy_version)
);

CREATE INDEX IF NOT EXISTS idx_rp_code
  ON risk_policy (policy_code);

CREATE TABLE IF NOT EXISTS risk_run (
  risk_run_id      TEXT NOT NULL PRIMARY KEY,
  idempotency_key  TEXT NOT NULL UNIQUE,
  policy_hash      TEXT NOT NULL DEFAULT '',
  account_id       TEXT NOT NULL DEFAULT '',
  portfolio_id     TEXT NOT NULL DEFAULT '',
  apply_id         TEXT NOT NULL DEFAULT '',
  trading_date     TEXT NOT NULL DEFAULT '',
  verdict          TEXT NOT NULL DEFAULT 'ALLOW',
  n_intents        INTEGER NOT NULL DEFAULT 0,
  n_violations     INTEGER NOT NULL DEFAULT 0,
  storage_uri      TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rr_account
  ON risk_run (account_id);

CREATE INDEX IF NOT EXISTS idx_rr_policy
  ON risk_run (policy_hash);

CREATE TABLE IF NOT EXISTS risk_decision_event (
  event_id         TEXT NOT NULL PRIMARY KEY,
  risk_run_id      TEXT NOT NULL,
  rule_code        TEXT NOT NULL DEFAULT '',
  decision         TEXT NOT NULL DEFAULT '',
  severity         TEXT NOT NULL DEFAULT 'P0',
  instrument_key   TEXT NOT NULL DEFAULT '',
  message          TEXT NOT NULL DEFAULT '',
  original_value   REAL NOT NULL DEFAULT 0,
  limit_value      REAL NOT NULL DEFAULT 0,
  payload_json     TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rde_run
  ON risk_decision_event (risk_run_id);

CREATE INDEX IF NOT EXISTS idx_rde_rule
  ON risk_decision_event (rule_code);

CREATE INDEX IF NOT EXISTS idx_rde_inst
  ON risk_decision_event (instrument_key);
