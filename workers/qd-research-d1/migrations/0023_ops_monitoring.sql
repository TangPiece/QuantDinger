-- Phase 6H：Ops Monitoring / Audit / Alert（大 payload 在 R2）

CREATE TABLE IF NOT EXISTS ops_health_snapshot (
  snapshot_id       TEXT NOT NULL PRIMARY KEY,
  captured_at       TEXT,
  overall_status    TEXT NOT NULL DEFAULT 'HEALTHY',
  health_json       TEXT NOT NULL DEFAULT '{}',
  counters_json     TEXT NOT NULL DEFAULT '{}',
  engine_version    TEXT NOT NULL DEFAULT 'qd_ops@1',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ops_health_captured
  ON ops_health_snapshot (captured_at);

CREATE TABLE IF NOT EXISTS ops_audit_event (
  event_id          TEXT NOT NULL PRIMARY KEY,
  event_type        TEXT NOT NULL DEFAULT '',
  timestamp         TEXT,
  actor_type        TEXT NOT NULL DEFAULT 'SYSTEM',
  actor_id          TEXT NOT NULL DEFAULT '',
  trace_id          TEXT NOT NULL DEFAULT '',
  account_id        TEXT NOT NULL DEFAULT '',
  strategy_id       TEXT NOT NULL DEFAULT '',
  order_id          TEXT NOT NULL DEFAULT '',
  entity_type       TEXT NOT NULL DEFAULT '',
  entity_id         TEXT NOT NULL DEFAULT '',
  reason            TEXT NOT NULL DEFAULT '',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ops_audit_trace
  ON ops_audit_event (trace_id);
CREATE INDEX IF NOT EXISTS idx_ops_audit_account
  ON ops_audit_event (account_id);
CREATE INDEX IF NOT EXISTS idx_ops_audit_order
  ON ops_audit_event (order_id);

CREATE TABLE IF NOT EXISTS ops_alert_rule (
  rule_id               TEXT NOT NULL PRIMARY KEY,
  enabled               INTEGER NOT NULL DEFAULT 1,
  metric_or_signal      TEXT NOT NULL DEFAULT '',
  severity              TEXT NOT NULL DEFAULT 'WARNING',
  threshold             REAL NOT NULL DEFAULT 0,
  comparison            TEXT NOT NULL DEFAULT 'GT',
  description           TEXT NOT NULL DEFAULT '',
  safety_source_kind    TEXT NOT NULL DEFAULT '',
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ops_alert_event (
  alert_id          TEXT NOT NULL PRIMARY KEY,
  rule_id           TEXT NOT NULL DEFAULT '',
  severity          TEXT NOT NULL DEFAULT 'WARNING',
  fired_at          TEXT,
  message           TEXT NOT NULL DEFAULT '',
  account_id        TEXT NOT NULL DEFAULT '',
  strategy_id       TEXT NOT NULL DEFAULT '',
  trace_id          TEXT NOT NULL DEFAULT '',
  incident_id       TEXT NOT NULL DEFAULT '',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ops_alert_incident
  ON ops_alert_event (incident_id);

CREATE TABLE IF NOT EXISTS ops_incident (
  incident_id           TEXT NOT NULL PRIMARY KEY,
  title                 TEXT NOT NULL DEFAULT '',
  severity              TEXT NOT NULL DEFAULT 'WARNING',
  status                TEXT NOT NULL DEFAULT 'OPEN',
  account_id            TEXT NOT NULL DEFAULT '',
  strategy_id           TEXT NOT NULL DEFAULT '',
  trace_id              TEXT NOT NULL DEFAULT '',
  opened_at             TEXT,
  updated_at            TEXT,
  resolved_at           TEXT,
  timeline_event_ids_json TEXT NOT NULL DEFAULT '[]',
  alert_ids_json        TEXT NOT NULL DEFAULT '[]',
  metadata_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ops_slo_definition (
  slo_id            TEXT NOT NULL PRIMARY KEY,
  name              TEXT NOT NULL DEFAULT '',
  target_ratio      REAL NOT NULL DEFAULT 0.999,
  window_sec        REAL NOT NULL DEFAULT 86400,
  metric_name       TEXT NOT NULL DEFAULT '',
  enabled           INTEGER NOT NULL DEFAULT 1,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);
