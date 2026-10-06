-- Phase 5D：Qlib Strategy Adapter Run Registry（明细在 R2）

CREATE TABLE IF NOT EXISTS research_qlib_run (
  qlib_run_hash       TEXT NOT NULL PRIMARY KEY,
  strategy_hash       TEXT NOT NULL,
  start_date          TEXT NOT NULL,
  end_date            TEXT NOT NULL,
  execution_policy    TEXT NOT NULL DEFAULT 'NEXT_OPEN',
  realism             TEXT NOT NULL DEFAULT 'GROSS',
  market_rule         TEXT NOT NULL DEFAULT '',
  dataset_ref         TEXT NOT NULL DEFAULT '',
  dataset_hash        TEXT NOT NULL DEFAULT '',
  materialization_id  TEXT NOT NULL DEFAULT '',
  backtest_hash       TEXT NOT NULL DEFAULT '',
  compatibility_json  TEXT NOT NULL DEFAULT '{}',
  metrics_json        TEXT NOT NULL DEFAULT '{}',
  engine_version      TEXT NOT NULL DEFAULT 'qlib_strategy_adapter@1',
  recorder_id         TEXT NOT NULL DEFAULT '',
  storage_uri         TEXT NOT NULL DEFAULT '',
  checksum            TEXT,
  created_at          TEXT NOT NULL,
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rqr_strategy
  ON research_qlib_run (strategy_hash);

CREATE INDEX IF NOT EXISTS idx_rqr_dataset
  ON research_qlib_run (dataset_hash);

CREATE INDEX IF NOT EXISTS idx_rqr_realism
  ON research_qlib_run (realism);
