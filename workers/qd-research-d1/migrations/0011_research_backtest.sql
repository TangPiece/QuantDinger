-- Phase 5B：Research Backtest Registry（日明细在 R2）

CREATE TABLE IF NOT EXISTS research_backtest_run (
  backtest_hash                 TEXT NOT NULL PRIMARY KEY,
  strategy_hash                 TEXT NOT NULL,
  start_date                    TEXT NOT NULL,
  end_date                      TEXT NOT NULL,
  execution_policy              TEXT NOT NULL DEFAULT 'NEXT_OPEN',
  benchmark_mode                TEXT NOT NULL DEFAULT 'NONE',
  benchmark_instrument_key      TEXT NOT NULL DEFAULT '',
  metrics_json                  TEXT NOT NULL DEFAULT '{}',
  benchmark_metrics_json        TEXT NOT NULL DEFAULT '{}',
  engine_version                TEXT NOT NULL DEFAULT 'qd_research_backtest@1',
  return_calculation_version    TEXT NOT NULL DEFAULT 'research_nav@1',
  storage_uri                   TEXT NOT NULL DEFAULT '',
  checksum                      TEXT,
  created_at                    TEXT NOT NULL,
  metadata_json                 TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rbr_strategy
  ON research_backtest_run (strategy_hash);

CREATE INDEX IF NOT EXISTS idx_rbr_window
  ON research_backtest_run (start_date, end_date);
