-- Phase 4F：Factor Stability / Decay Summary（明细在 R2）

CREATE TABLE IF NOT EXISTS factor_stability_evaluation (
  stability_hash                 TEXT NOT NULL,
  horizon                        INTEGER NOT NULL,
  evaluation_hash                TEXT NOT NULL,
  factor_dataset_id              TEXT NOT NULL DEFAULT '',
  rolling_windows_json           TEXT NOT NULL DEFAULT '[]',
  decay_summary_json             TEXT NOT NULL DEFAULT '[]',
  regime_summary_json            TEXT NOT NULL DEFAULT '[]',
  ic_stability_metrics_json      TEXT NOT NULL DEFAULT '{}',
  group_stability_metrics_json   TEXT NOT NULL DEFAULT '{}',
  stability_version              TEXT NOT NULL DEFAULT 'qd_factor_stability@1',
  storage_uri                    TEXT NOT NULL DEFAULT '',
  checksum                       TEXT,
  created_at                     TEXT NOT NULL,
  metadata_json                  TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (stability_hash, horizon)
);

CREATE INDEX IF NOT EXISTS idx_factor_stability_eval
  ON factor_stability_evaluation (evaluation_hash);

CREATE INDEX IF NOT EXISTS idx_factor_stability_factor
  ON factor_stability_evaluation (factor_dataset_id);
