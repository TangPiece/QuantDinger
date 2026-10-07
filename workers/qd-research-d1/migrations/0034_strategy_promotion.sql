-- Phase 8D：Strategy Promotion Pipeline（环境晋升 SSOT，非 8B candidate_promotion）

CREATE TABLE IF NOT EXISTS strategy_promotion_policy (
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  transition_key         TEXT NOT NULL DEFAULT '',
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  rules_json             TEXT NOT NULL DEFAULT '{}',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_promotion@1',
  description            TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (policy_id, policy_version)
);

CREATE TABLE IF NOT EXISTS strategy_promotion_request (
  request_id             TEXT NOT NULL PRIMARY KEY,
  pipeline_run_id        TEXT NOT NULL DEFAULT '',
  idempotency_key        TEXT NOT NULL DEFAULT '',
  strategy_code          TEXT NOT NULL,
  candidate_id           TEXT NOT NULL DEFAULT '',
  validation_id          TEXT NOT NULL DEFAULT '',
  strategy_version       TEXT NOT NULL DEFAULT '',
  version_id             TEXT NOT NULL DEFAULT '',
  content_hash           TEXT NOT NULL DEFAULT '',
  from_environment       TEXT NOT NULL DEFAULT 'REGISTERED',
  to_environment         TEXT NOT NULL,
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  status                 TEXT NOT NULL DEFAULT 'PENDING',
  operator               TEXT NOT NULL DEFAULT '',
  approvals_json         TEXT NOT NULL DEFAULT '[]',
  created_at             TEXT NOT NULL DEFAULT '',
  updated_at             TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_promotion@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_spr_idempotency
  ON strategy_promotion_request(strategy_code, idempotency_key);

CREATE INDEX IF NOT EXISTS idx_spr_strategy_code ON strategy_promotion_request(strategy_code);

CREATE TABLE IF NOT EXISTS strategy_promotion_run (
  pipeline_run_id        TEXT NOT NULL PRIMARY KEY,
  request_id             TEXT NOT NULL,
  strategy_code          TEXT NOT NULL,
  from_environment       TEXT NOT NULL DEFAULT '',
  to_environment         TEXT NOT NULL DEFAULT '',
  policy_id              TEXT NOT NULL DEFAULT '',
  policy_version         TEXT NOT NULL DEFAULT '',
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  status                 TEXT NOT NULL DEFAULT 'IN_PROGRESS',
  stages_json            TEXT NOT NULL DEFAULT '[]',
  session_id             TEXT NOT NULL DEFAULT '',
  governance_state       TEXT NOT NULL DEFAULT '',
  started_at             TEXT NOT NULL DEFAULT '',
  completed_at           TEXT NOT NULL DEFAULT '',
  operator               TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_promotion@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sprun_strategy ON strategy_promotion_run(strategy_code);
CREATE INDEX IF NOT EXISTS idx_sprun_status ON strategy_promotion_run(status);

CREATE TABLE IF NOT EXISTS strategy_promotion_rollback (
  rollback_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  from_version           TEXT NOT NULL DEFAULT '',
  to_version             TEXT NOT NULL DEFAULT '',
  reason                 TEXT NOT NULL DEFAULT '',
  operator               TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_promotion@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sproll_strategy ON strategy_promotion_rollback(strategy_code);
