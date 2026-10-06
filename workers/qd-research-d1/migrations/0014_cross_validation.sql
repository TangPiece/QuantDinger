-- Phase 5E：Qlib ↔ QuantDinger Cross Validation Registry（明细在 R2）

CREATE TABLE IF NOT EXISTS research_cross_validation (
  cv_hash                   TEXT NOT NULL PRIMARY KEY,
  strategy_hash             TEXT NOT NULL,
  backtest_hash             TEXT NOT NULL DEFAULT '',
  qlib_run_hash             TEXT NOT NULL DEFAULT '',
  start_date                TEXT NOT NULL DEFAULT '',
  end_date                  TEXT NOT NULL DEFAULT '',
  realism                   TEXT NOT NULL DEFAULT 'GROSS',
  execution_policy          TEXT NOT NULL DEFAULT 'NEXT_OPEN',
  status                    TEXT NOT NULL DEFAULT 'FAILED',
  layer_results_json        TEXT NOT NULL DEFAULT '{}',
  attribution_json          TEXT NOT NULL DEFAULT '{}',
  metrics_side_by_side_json TEXT NOT NULL DEFAULT '{}',
  engine_version            TEXT NOT NULL DEFAULT 'qd_cross_validation@1',
  storage_uri               TEXT NOT NULL DEFAULT '',
  checksum                  TEXT,
  created_at                TEXT NOT NULL,
  metadata_json             TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rcv_strategy
  ON research_cross_validation (strategy_hash);

CREATE INDEX IF NOT EXISTS idx_rcv_status
  ON research_cross_validation (status);

CREATE INDEX IF NOT EXISTS idx_rcv_backtest
  ON research_cross_validation (backtest_hash);

CREATE INDEX IF NOT EXISTS idx_rcv_qlib
  ON research_cross_validation (qlib_run_hash);
