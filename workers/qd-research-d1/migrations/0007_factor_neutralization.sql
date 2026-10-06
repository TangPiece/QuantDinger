-- Phase 4G：Factor Neutralization Summary（明细在 R2）

CREATE TABLE IF NOT EXISTS factor_neutralization (
  neutralization_hash            TEXT NOT NULL PRIMARY KEY,
  factor_dataset_id              TEXT NOT NULL,
  factor_dataset_hash            TEXT NOT NULL DEFAULT '',
  method                         TEXT NOT NULL DEFAULT 'REGRESSION',
  targets_json                   TEXT NOT NULL DEFAULT '[]',
  r_squared_mean                 REAL,
  diagnostics_json               TEXT NOT NULL DEFAULT '{}',
  neutralized_factor_dataset_id   TEXT NOT NULL DEFAULT '',
  neutralization_version         TEXT NOT NULL DEFAULT 'qd_factor_neutralization@1',
  storage_uri                    TEXT NOT NULL DEFAULT '',
  checksum                       TEXT,
  created_at                     TEXT NOT NULL,
  metadata_json                  TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_factor_neut_src
  ON factor_neutralization (factor_dataset_id);

CREATE INDEX IF NOT EXISTS idx_factor_neut_out
  ON factor_neutralization (neutralized_factor_dataset_id);
