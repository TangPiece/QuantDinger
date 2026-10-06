-- Phase 4E：Group Return / Turnover Summary（明细在 R2）

CREATE TABLE IF NOT EXISTS factor_group_evaluation (
  group_evaluation_hash      TEXT NOT NULL,
  horizon                    INTEGER NOT NULL,
  evaluation_hash            TEXT NOT NULL,
  factor_dataset_id          TEXT NOT NULL DEFAULT '',
  group_count                INTEGER NOT NULL DEFAULT 10,
  weighting_method           TEXT NOT NULL DEFAULT 'EQUAL_WEIGHT',
  direction                  TEXT NOT NULL DEFAULT 'POSITIVE',
  portfolio_mode             TEXT NOT NULL DEFAULT 'BOTH',
  long_group                 INTEGER NOT NULL DEFAULT 1,
  short_group                INTEGER NOT NULL DEFAULT 10,
  mean_long_return           REAL,
  mean_short_return          REAL,
  mean_long_short_return     REAL,
  mean_turnover              REAL,
  mean_estimated_cost        REAL,
  mean_net_long_short_return REAL,
  valid_day_count            INTEGER NOT NULL DEFAULT 0,
  total_day_count            INTEGER NOT NULL DEFAULT 0,
  group_version              TEXT NOT NULL DEFAULT 'qd_factor_groups@1',
  storage_uri                TEXT NOT NULL DEFAULT '',
  checksum                   TEXT,
  created_at                 TEXT NOT NULL,
  metadata_json              TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (group_evaluation_hash, horizon)
);

CREATE INDEX IF NOT EXISTS idx_factor_group_eval_hash
  ON factor_group_evaluation (evaluation_hash);
