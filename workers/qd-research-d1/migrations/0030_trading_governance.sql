-- Phase 7E：Trading Governance（Gradual Scale / 多策略多账户）

CREATE TABLE IF NOT EXISTS gov_strategy_version (
  strategy_id       TEXT NOT NULL,
  strategy_version  TEXT NOT NULL,
  model_version     TEXT NOT NULL DEFAULT '',
  dataset_hash      TEXT NOT NULL DEFAULT '',
  feature_version   TEXT NOT NULL DEFAULT '',
  content_hash      TEXT NOT NULL DEFAULT '',
  is_live           INTEGER NOT NULL DEFAULT 0,
  engine_version    TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json     TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (strategy_id, strategy_version)
);

CREATE TABLE IF NOT EXISTS gov_strategy_lifecycle (
  strategy_id              TEXT NOT NULL PRIMARY KEY,
  state                    TEXT NOT NULL DEFAULT 'DRAFT',
  active_version           TEXT NOT NULL DEFAULT '',
  previous_stable_version  TEXT NOT NULL DEFAULT '',
  scale_level              TEXT NOT NULL DEFAULT 'L0_SHADOW',
  updated_at               TEXT NOT NULL DEFAULT '',
  engine_version           TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json            TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_capital_allocation (
  account_id           TEXT NOT NULL,
  strategy_id          TEXT NOT NULL,
  allocated_notional   REAL NOT NULL DEFAULT 0,
  reserve_notional     REAL NOT NULL DEFAULT 0,
  used_notional        REAL NOT NULL DEFAULT 0,
  engine_version       TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json        TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (account_id, strategy_id)
);

CREATE TABLE IF NOT EXISTS gov_risk_budget (
  scope_key        TEXT NOT NULL PRIMARY KEY,
  account_id       TEXT NOT NULL DEFAULT '',
  portfolio_id     TEXT NOT NULL DEFAULT '',
  strategy_id      TEXT NOT NULL DEFAULT '',
  layers_json      TEXT NOT NULL DEFAULT '[]',
  engine_version   TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_capacity (
  strategy_id              TEXT NOT NULL PRIMARY KEY,
  max_notional             REAL NOT NULL DEFAULT 0,
  max_order_size           REAL NOT NULL DEFAULT 0,
  max_participation_rate   REAL NOT NULL DEFAULT 0,
  max_daily_turnover       REAL NOT NULL DEFAULT 0,
  engine_version           TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json            TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_scale_state (
  strategy_id         TEXT NOT NULL PRIMARY KEY,
  account_id          TEXT NOT NULL DEFAULT '',
  current_level       TEXT NOT NULL DEFAULT 'L0_SHADOW',
  pending_level       TEXT NOT NULL DEFAULT '',
  live_env_approved   INTEGER NOT NULL DEFAULT 0,
  updated_at          TEXT NOT NULL DEFAULT '',
  engine_version      TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_scale_approval (
  approval_id           TEXT NOT NULL PRIMARY KEY,
  kind                  TEXT NOT NULL DEFAULT 'SCALE_UP',
  strategy_id           TEXT NOT NULL DEFAULT '',
  account_id            TEXT NOT NULL DEFAULT '',
  operator_actor        TEXT NOT NULL DEFAULT '',
  approval_token_hash   TEXT NOT NULL DEFAULT '',
  status                TEXT NOT NULL DEFAULT 'PENDING',
  from_scale            TEXT NOT NULL DEFAULT '',
  to_scale              TEXT NOT NULL DEFAULT '',
  approved_at           TEXT NOT NULL DEFAULT '',
  engine_version        TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_account_registry (
  account_id       TEXT NOT NULL PRIMARY KEY,
  label            TEXT NOT NULL DEFAULT '',
  environment      TEXT NOT NULL DEFAULT 'LIVE_CONTROLLED',
  status           TEXT NOT NULL DEFAULT 'ACTIVE',
  engine_version   TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_strategy_account_bind (
  strategy_id      TEXT NOT NULL PRIMARY KEY,
  account_id       TEXT NOT NULL DEFAULT '',
  portfolio_id     TEXT NOT NULL DEFAULT '',
  engine_version   TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_attribution_snapshot (
  snapshot_id      TEXT NOT NULL PRIMARY KEY,
  account_id       TEXT NOT NULL DEFAULT '',
  rows_json        TEXT NOT NULL DEFAULT '[]',
  engine_version   TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gov_aggregation_run (
  run_id           TEXT NOT NULL PRIMARY KEY,
  account_id       TEXT NOT NULL DEFAULT '',
  storage_uri      TEXT NOT NULL DEFAULT '',
  engine_version   TEXT NOT NULL DEFAULT 'qd_governance@1',
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_gov_scale_approval_strategy
  ON gov_scale_approval (strategy_id);

CREATE INDEX IF NOT EXISTS idx_gov_capital_allocation_account
  ON gov_capital_allocation (account_id);
