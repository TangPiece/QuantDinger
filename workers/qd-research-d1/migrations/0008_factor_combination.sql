-- Phase 4H：Factor Combination Summary（明细在 R2）

CREATE TABLE IF NOT EXISTS factor_combination (
  combination_hash                 TEXT NOT NULL PRIMARY KEY,
  member_factor_dataset_ids_json    TEXT NOT NULL DEFAULT '[]',
  normalize                        TEXT NOT NULL DEFAULT 'RANK',
  weight_method                    TEXT NOT NULL DEFAULT 'EQUAL',
  weights_json                     TEXT NOT NULL DEFAULT '{}',
  correlation_summary_json         TEXT NOT NULL DEFAULT '{}',
  redundancy_pairs_json            TEXT NOT NULL DEFAULT '[]',
  composite_factor_dataset_id       TEXT NOT NULL DEFAULT '',
  combination_version              TEXT NOT NULL DEFAULT 'qd_factor_combination@1',
  storage_uri                      TEXT NOT NULL DEFAULT '',
  checksum                         TEXT,
  created_at                       TEXT NOT NULL,
  metadata_json                    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_factor_comb_composite
  ON factor_combination (composite_factor_dataset_id);
