-- Phase 8C：Strategy Validation Gate（Policy + 不可变 Run）

CREATE TABLE IF NOT EXISTS strategy_validation_policy (
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  rules_json             TEXT NOT NULL DEFAULT '{}',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_validation@1',
  description            TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (policy_id, policy_version)
);

CREATE TABLE IF NOT EXISTS strategy_validation_run (
  validation_id          TEXT NOT NULL PRIMARY KEY,
  candidate_id           TEXT NOT NULL,
  candidate_version      TEXT NOT NULL DEFAULT '',
  dataset_hash           TEXT NOT NULL DEFAULT '',
  snapshot_id            TEXT NOT NULL DEFAULT '',
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  validator_version      TEXT NOT NULL DEFAULT 'qd_strategy_validation@1',
  started_at             TEXT NOT NULL DEFAULT '',
  completed_at           TEXT NOT NULL DEFAULT '',
  status                 TEXT NOT NULL DEFAULT 'VALIDATING',
  operator               TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_validation@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_svr_candidate_id ON strategy_validation_run(candidate_id);
CREATE INDEX IF NOT EXISTS idx_svr_policy ON strategy_validation_run(policy_id, policy_version);
