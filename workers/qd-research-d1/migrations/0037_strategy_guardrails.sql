-- Phase 8G：Strategy Governance & Auto Guardrails（Runtime 与 Lifecycle 分离）

CREATE TABLE IF NOT EXISTS guardrail_policy (
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  auto_execute           INTEGER NOT NULL DEFAULT 1,
  auto_action_policy_id  TEXT NOT NULL DEFAULT '',
  auto_action_policy_version TEXT NOT NULL DEFAULT '',
  action_matrix_json     TEXT NOT NULL DEFAULT '[]',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_guardrails@1',
  description            TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (policy_id, policy_version)
);

CREATE TABLE IF NOT EXISTS auto_action_policy (
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  auto_allowed_json      TEXT NOT NULL DEFAULT '[]',
  auto_forbidden_json    TEXT NOT NULL DEFAULT '[]',
  auto_resume            INTEGER NOT NULL DEFAULT 0,
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_guardrails@1',
  description            TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (policy_id, policy_version)
);

CREATE TABLE IF NOT EXISTS strategy_runtime_state (
  strategy_code          TEXT NOT NULL PRIMARY KEY,
  runtime_status         TEXT NOT NULL DEFAULT 'ACTIVE',
  lifecycle_phase        TEXT NOT NULL DEFAULT 'UNKNOWN',
  throttle_tier          TEXT NOT NULL DEFAULT 'NORMAL',
  throttle_multiplier    REAL NOT NULL DEFAULT 1.0,
  policy_id              TEXT NOT NULL DEFAULT '',
  policy_version         TEXT NOT NULL DEFAULT '',
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  last_incident_id       TEXT NOT NULL DEFAULT '',
  recovery_check_passed  INTEGER NOT NULL DEFAULT 0,
  last_evaluated_at      TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_guardrails@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS governance_incident (
  incident_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  status                 TEXT NOT NULL DEFAULT 'DETECTED',
  severity               TEXT NOT NULL DEFAULT 'CRITICAL',
  category               TEXT NOT NULL DEFAULT 'SYSTEM',
  recommended_action     TEXT NOT NULL DEFAULT 'REVIEW',
  alert_id               TEXT NOT NULL DEFAULT '',
  message                TEXT NOT NULL DEFAULT '',
  requires_decision      INTEGER NOT NULL DEFAULT 0,
  opened_at              TEXT NOT NULL DEFAULT '',
  resolved_at            TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_guardrails@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_gi_strategy ON governance_incident(strategy_code);

CREATE TABLE IF NOT EXISTS governance_decision (
  decision_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  incident_id            TEXT NOT NULL DEFAULT '',
  decision_type          TEXT NOT NULL DEFAULT 'CONTINUE',
  status                 TEXT NOT NULL DEFAULT 'PENDING',
  operator               TEXT NOT NULL DEFAULT '',
  reason                 TEXT NOT NULL DEFAULT '',
  to_version             TEXT NOT NULL DEFAULT '',
  submitted_at           TEXT NOT NULL DEFAULT '',
  approved_at            TEXT NOT NULL DEFAULT '',
  executed_at            TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_guardrails@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_gd_strategy ON governance_decision(strategy_code);

CREATE TABLE IF NOT EXISTS governance_event (
  event_id               TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  event_type             TEXT NOT NULL DEFAULT 'GUARDRAIL_BREACH',
  runtime_status         TEXT NOT NULL DEFAULT 'ACTIVE',
  lifecycle_phase        TEXT NOT NULL DEFAULT 'UNKNOWN',
  severity               TEXT NOT NULL DEFAULT 'INFO',
  category               TEXT NOT NULL DEFAULT 'SYSTEM',
  incident_id            TEXT NOT NULL DEFAULT '',
  decision_id            TEXT NOT NULL DEFAULT '',
  message                TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_guardrails@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ge8g_strategy ON governance_event(strategy_code);

CREATE TABLE IF NOT EXISTS guardrail_rollback_record (
  rollback_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  from_version           TEXT NOT NULL DEFAULT '',
  to_version             TEXT NOT NULL DEFAULT '',
  from_model_version     TEXT NOT NULL DEFAULT '',
  to_model_version       TEXT NOT NULL DEFAULT '',
  from_dataset_hash      TEXT NOT NULL DEFAULT '',
  to_dataset_hash        TEXT NOT NULL DEFAULT '',
  decision_id            TEXT NOT NULL DEFAULT '',
  reason                 TEXT NOT NULL DEFAULT '',
  operator               TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_guardrails@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_grb_strategy ON guardrail_rollback_record(strategy_code);
