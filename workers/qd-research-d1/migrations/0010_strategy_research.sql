-- Phase 5A：Strategy Research Registry（明细在 R2）

CREATE TABLE IF NOT EXISTS research_strategy (
  strategy_code   TEXT NOT NULL PRIMARY KEY,
  name            TEXT NOT NULL DEFAULT '',
  description     TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at      TEXT NOT NULL,
  metadata_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS research_strategy_version (
  strategy_hash              TEXT NOT NULL PRIMARY KEY,
  strategy_code              TEXT NOT NULL,
  strategy_version_label     TEXT NOT NULL DEFAULT 'qd_strategy_research@1',
  factor_dataset_id          TEXT NOT NULL DEFAULT '',
  portfolio_hash             TEXT NOT NULL DEFAULT '',
  evaluation_hash            TEXT NOT NULL DEFAULT '',
  signal_definition_json     TEXT NOT NULL DEFAULT '{}',
  rebalance_rule_json        TEXT NOT NULL DEFAULT '{}',
  holding_rule_json          TEXT NOT NULL DEFAULT '{}',
  universe_code              TEXT NOT NULL DEFAULT '',
  snapshot_id                TEXT NOT NULL DEFAULT '',
  signal_row_count           INTEGER NOT NULL DEFAULT 0,
  position_row_count         INTEGER NOT NULL DEFAULT 0,
  storage_uri                TEXT NOT NULL DEFAULT '',
  checksum                   TEXT,
  created_at                 TEXT NOT NULL,
  metadata_json              TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rsv_code
  ON research_strategy_version (strategy_code);

CREATE INDEX IF NOT EXISTS idx_rsv_portfolio
  ON research_strategy_version (portfolio_hash);

CREATE INDEX IF NOT EXISTS idx_rsv_factor
  ON research_strategy_version (factor_dataset_id);
