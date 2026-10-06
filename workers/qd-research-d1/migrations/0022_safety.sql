-- Phase 6G：Safety Registry（事件明细在 R2；热路径 state/kill_switch 走 D1）

CREATE TABLE IF NOT EXISTS safety_rule (
  rule_id           TEXT NOT NULL PRIMARY KEY,
  enabled           INTEGER NOT NULL DEFAULT 1,
  threshold         REAL NOT NULL DEFAULT 0,
  action            TEXT NOT NULL DEFAULT 'BLOCK_NEW_ORDER',
  scope             TEXT NOT NULL DEFAULT 'ACCOUNT',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS safety_state (
  scope             TEXT NOT NULL,
  scope_id          TEXT NOT NULL,
  state             TEXT NOT NULL DEFAULT 'NORMAL',
  acknowledged      INTEGER NOT NULL DEFAULT 0,
  reason            TEXT NOT NULL DEFAULT '',
  updated_at        TEXT,
  metadata_json     TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (scope, scope_id)
);

CREATE INDEX IF NOT EXISTS idx_safety_state_scope
  ON safety_state (scope, scope_id);

CREATE TABLE IF NOT EXISTS safety_event (
  event_id          TEXT NOT NULL PRIMARY KEY,
  scope             TEXT NOT NULL DEFAULT 'ACCOUNT',
  scope_id          TEXT NOT NULL DEFAULT '',
  rule              TEXT NOT NULL DEFAULT '',
  severity          TEXT NOT NULL DEFAULT 'WARNING',
  state_before      TEXT NOT NULL DEFAULT 'NORMAL',
  state_after       TEXT NOT NULL DEFAULT 'HALTED',
  reason            TEXT NOT NULL DEFAULT '',
  trigger_value     REAL NOT NULL DEFAULT 0,
  threshold         REAL NOT NULL DEFAULT 0,
  created_at        TEXT,
  resolved_at       TEXT,
  operator          TEXT NOT NULL DEFAULT '',
  acknowledged      INTEGER NOT NULL DEFAULT 0,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_safety_event_scope
  ON safety_event (scope, scope_id);
CREATE INDEX IF NOT EXISTS idx_safety_event_rule
  ON safety_event (rule);

CREATE TABLE IF NOT EXISTS kill_switch (
  scope             TEXT NOT NULL,
  scope_id          TEXT NOT NULL,
  engaged           INTEGER NOT NULL DEFAULT 0,
  reason            TEXT NOT NULL DEFAULT '',
  engaged_at        TEXT,
  engaged_by        TEXT NOT NULL DEFAULT '',
  metadata_json     TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (scope, scope_id)
);

CREATE TABLE IF NOT EXISTS safety_hard_limit_audit (
  audit_id          TEXT NOT NULL PRIMARY KEY,
  rule_id           TEXT NOT NULL DEFAULT '',
  attempted_value   REAL NOT NULL DEFAULT 0,
  hard_ceiling      REAL NOT NULL DEFAULT 0,
  operator          TEXT NOT NULL DEFAULT '',
  created_at        TEXT NOT NULL,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);
