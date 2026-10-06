-- Phase 4A：Factor Lab Foundation — 扩展 feature + factor_dataset 索引
-- Factor Values 仍在 R2；本 migration 只扩展 Registry。

ALTER TABLE feature ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE feature ADD COLUMN factor_type TEXT NOT NULL DEFAULT 'CUSTOM';
ALTER TABLE feature ADD COLUMN computation_engine TEXT NOT NULL DEFAULT 'quantdinger';
ALTER TABLE feature ADD COLUMN engine_version TEXT NOT NULL DEFAULT '';
ALTER TABLE feature ADD COLUMN universe TEXT;
ALTER TABLE feature ADD COLUMN information_policy TEXT NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE feature ADD COLUMN schema_version TEXT NOT NULL DEFAULT 'factor_daily_long@1';
ALTER TABLE feature ADD COLUMN factor_hash TEXT;

CREATE TABLE IF NOT EXISTS factor_dataset (
  factor_dataset_id TEXT PRIMARY KEY,
  factor_ref        TEXT NOT NULL,
  factor_hash       TEXT NOT NULL,
  dataset_hash      TEXT NOT NULL,
  snapshot_id       TEXT NOT NULL,
  universe_code     TEXT NOT NULL DEFAULT '',
  frequency         TEXT NOT NULL DEFAULT '1d',
  start_date        TEXT NOT NULL DEFAULT '',
  end_date          TEXT NOT NULL DEFAULT '',
  storage_uri       TEXT NOT NULL DEFAULT '',
  checksum          TEXT,
  row_count         INTEGER,
  layout            TEXT NOT NULL DEFAULT 'long',
  schema_version    TEXT NOT NULL DEFAULT 'factor_daily_long@1',
  status            TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at        TEXT NOT NULL,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_factor_dataset_factor_ref
  ON factor_dataset (factor_ref);

CREATE INDEX IF NOT EXISTS idx_factor_dataset_hash
  ON factor_dataset (factor_hash, dataset_hash);
