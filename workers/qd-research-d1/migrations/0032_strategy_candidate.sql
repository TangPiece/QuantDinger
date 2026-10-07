-- Phase 8B：Strategy Candidate（研究证据 → 可治理候选 + Promotion 审计）

CREATE TABLE IF NOT EXISTS strategy_candidate (
  candidate_id              TEXT NOT NULL PRIMARY KEY,
  strategy_code             TEXT NOT NULL,
  candidate_version         TEXT NOT NULL,
  experiment_id             TEXT NOT NULL DEFAULT '',
  backtest_hash             TEXT NOT NULL DEFAULT '',
  model_version             TEXT NOT NULL DEFAULT '',
  model_artifact_id         TEXT NOT NULL DEFAULT '',
  dataset_hash              TEXT NOT NULL DEFAULT '',
  snapshot_id               TEXT NOT NULL DEFAULT '',
  feature_version           TEXT NOT NULL DEFAULT '',
  processor_version         TEXT NOT NULL DEFAULT '',
  processor_hash            TEXT NOT NULL DEFAULT '',
  strategy_hash             TEXT NOT NULL DEFAULT '',
  strategy_definition_json  TEXT NOT NULL DEFAULT '{}',
  risk_policy_ref           TEXT NOT NULL DEFAULT '',
  execution_policy_ref      TEXT NOT NULL DEFAULT 'NEXT_OPEN',
  evaluation_hash           TEXT NOT NULL DEFAULT '',
  cv_hash                   TEXT NOT NULL DEFAULT '',
  content_hash              TEXT NOT NULL DEFAULT '',
  source                    TEXT NOT NULL DEFAULT 'RESEARCH',
  status                    TEXT NOT NULL DEFAULT 'DRAFT',
  lineage_frozen_at         TEXT NOT NULL DEFAULT '',
  created_at                TEXT NOT NULL DEFAULT '',
  storage_uri               TEXT NOT NULL DEFAULT '',
  engine_version            TEXT NOT NULL DEFAULT 'qd_strategy_candidate@1',
  metadata_json             TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS strategy_candidate_promotion (
  promotion_id            TEXT NOT NULL PRIMARY KEY,
  candidate_id            TEXT NOT NULL,
  source_type             TEXT NOT NULL DEFAULT 'EXPERIMENT',
  source_id               TEXT NOT NULL DEFAULT '',
  target_strategy_code    TEXT NOT NULL DEFAULT '',
  target_strategy_version TEXT NOT NULL DEFAULT '',
  version_id              TEXT NOT NULL DEFAULT '',
  from_state              TEXT NOT NULL DEFAULT '',
  to_state                TEXT NOT NULL DEFAULT '',
  dataset_hash            TEXT NOT NULL DEFAULT '',
  model_version           TEXT NOT NULL DEFAULT '',
  operator                TEXT NOT NULL DEFAULT '',
  reason                  TEXT NOT NULL DEFAULT '',
  status                  TEXT NOT NULL DEFAULT 'COMPLETED',
  created_at              TEXT NOT NULL DEFAULT '',
  engine_version          TEXT NOT NULL DEFAULT 'qd_strategy_candidate@1',
  metadata_json           TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_strategy_candidate_code ON strategy_candidate(strategy_code);
CREATE INDEX IF NOT EXISTS idx_strategy_candidate_hash ON strategy_candidate(strategy_hash);
CREATE INDEX IF NOT EXISTS idx_scp_candidate_id ON strategy_candidate_promotion(candidate_id);
