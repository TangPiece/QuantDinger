-- Phase 4C：Factor Evaluation Foundation — evaluation_dataset 索引
-- 评价明细在 R2 Parquet；本表只存 Registry / Summary 元数据。

CREATE TABLE IF NOT EXISTS evaluation_dataset (
  evaluation_hash       TEXT PRIMARY KEY,
  factor_dataset_id     TEXT NOT NULL,
  factor_dataset_hash   TEXT NOT NULL,
  snapshot_id           TEXT NOT NULL,
  universe_code         TEXT NOT NULL DEFAULT '',
  universe_version      TEXT NOT NULL DEFAULT '',
  start_date            TEXT NOT NULL DEFAULT '',
  end_date              TEXT NOT NULL DEFAULT '',
  return_spec_json      TEXT NOT NULL DEFAULT '{}',
  price_policy_json     TEXT NOT NULL DEFAULT '{}',
  evaluator_version     TEXT NOT NULL DEFAULT 'qd_factor_eval@1',
  mode                  TEXT NOT NULL DEFAULT 'CROSS_SECTIONAL',
  storage_uri           TEXT NOT NULL DEFAULT '',
  checksum              TEXT,
  row_count             INTEGER,
  schema_version        TEXT NOT NULL DEFAULT 'evaluation_panel@1',
  status                TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at            TEXT NOT NULL,
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_evaluation_dataset_factor
  ON evaluation_dataset (factor_dataset_id);

CREATE INDEX IF NOT EXISTS idx_evaluation_dataset_snapshot
  ON evaluation_dataset (snapshot_id, universe_code);
