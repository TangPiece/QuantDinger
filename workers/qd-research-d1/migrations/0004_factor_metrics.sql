-- Phase 4D：IC / RankIC Summary Registry（明细时间序列在 R2）

CREATE TABLE IF NOT EXISTS factor_evaluation_summary (
  metric_hash              TEXT NOT NULL,
  horizon                  INTEGER NOT NULL,
  evaluation_hash          TEXT NOT NULL,
  factor_dataset_id        TEXT NOT NULL DEFAULT '',
  mean_ic                  REAL,
  median_ic                REAL,
  std_ic                   REAL,
  min_ic                   REAL,
  max_ic                   REAL,
  ic_ir                    REAL,
  ic_t_stat                REAL,
  positive_ic_ratio        REAL,
  mean_rank_ic             REAL,
  median_rank_ic           REAL,
  std_rank_ic              REAL,
  min_rank_ic              REAL,
  max_rank_ic              REAL,
  rank_ic_ir               REAL,
  rank_ic_t_stat           REAL,
  positive_rank_ic_ratio   REAL,
  valid_day_count          INTEGER NOT NULL DEFAULT 0,
  total_day_count          INTEGER NOT NULL DEFAULT 0,
  direction                TEXT NOT NULL DEFAULT 'AUTO',
  metric_version           TEXT NOT NULL DEFAULT 'qd_factor_metrics@1',
  storage_uri              TEXT NOT NULL DEFAULT '',
  checksum                 TEXT,
  created_at               TEXT NOT NULL,
  metadata_json            TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (metric_hash, horizon)
);

CREATE INDEX IF NOT EXISTS idx_factor_eval_summary_eval
  ON factor_evaluation_summary (evaluation_hash);

CREATE INDEX IF NOT EXISTS idx_factor_eval_summary_factor
  ON factor_evaluation_summary (factor_dataset_id);
