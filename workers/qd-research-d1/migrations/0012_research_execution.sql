-- Phase 5C：Research Execution 字段（成本/规则指纹 + 归因）

ALTER TABLE research_backtest_run ADD COLUMN realism TEXT NOT NULL DEFAULT 'GROSS';
ALTER TABLE research_backtest_run ADD COLUMN market_rule TEXT NOT NULL DEFAULT '';
ALTER TABLE research_backtest_run ADD COLUMN execution_profile_version TEXT NOT NULL DEFAULT 'qd_research_execution@1';
ALTER TABLE research_backtest_run ADD COLUMN attribution_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_rbr_realism
  ON research_backtest_run (realism);

CREATE INDEX IF NOT EXISTS idx_rbr_market_rule
  ON research_backtest_run (market_rule);
