-- Phase 4I：Factor Portfolio Summary（明细在 R2）

CREATE TABLE IF NOT EXISTS factor_portfolio (
  portfolio_hash          TEXT NOT NULL PRIMARY KEY,
  factor_dataset_id       TEXT NOT NULL,
  evaluation_hash         TEXT NOT NULL DEFAULT '',
  construction_method     TEXT NOT NULL DEFAULT 'LONG_ONLY',
  weight_method           TEXT NOT NULL DEFAULT 'EQUAL_WEIGHT',
  rebalance_frequency     TEXT NOT NULL DEFAULT 'DAILY',
  selection_json          TEXT NOT NULL DEFAULT '{}',
  metrics_json            TEXT NOT NULL DEFAULT '{}',
  portfolio_version       TEXT NOT NULL DEFAULT 'qd_factor_portfolio@1',
  storage_uri             TEXT NOT NULL DEFAULT '',
  checksum                TEXT,
  created_at              TEXT NOT NULL,
  metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_factor_portfolio_factor
  ON factor_portfolio (factor_dataset_id);

CREATE INDEX IF NOT EXISTS idx_factor_portfolio_eval
  ON factor_portfolio (evaluation_hash);
