-- Phase 8F：Strategy Monitoring（观察记录，非自动降级）

CREATE TABLE IF NOT EXISTS strategy_alert_rule (
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  rules_json             TEXT NOT NULL DEFAULT '[]',
  market_data_json       TEXT NOT NULL DEFAULT '{}',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_monitoring@1',
  description            TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (policy_id, policy_version)
);

CREATE TABLE IF NOT EXISTS strategy_monitor_metric (
  metric_id              TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  category               TEXT NOT NULL DEFAULT 'SYSTEM',
  name                   TEXT NOT NULL DEFAULT '',
  value                  REAL NOT NULL DEFAULT 0,
  unit                   TEXT NOT NULL DEFAULT '',
  health                 TEXT NOT NULL DEFAULT 'UNKNOWN',
  window                 TEXT NOT NULL DEFAULT '5m',
  collected_at           TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  labels_json            TEXT NOT NULL DEFAULT '{}',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_monitoring@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_smm_strategy ON strategy_monitor_metric(strategy_code);
CREATE INDEX IF NOT EXISTS idx_smm_strategy_cat ON strategy_monitor_metric(strategy_code, category);

CREATE TABLE IF NOT EXISTS strategy_health_snapshot (
  snapshot_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  overall                TEXT NOT NULL DEFAULT 'UNKNOWN',
  dimensions_json        TEXT NOT NULL DEFAULT '[]',
  policy_id              TEXT NOT NULL DEFAULT '',
  policy_version         TEXT NOT NULL DEFAULT '',
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  evaluated_at           TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_monitoring@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_shs_strategy ON strategy_health_snapshot(strategy_code);

CREATE TABLE IF NOT EXISTS strategy_alert (
  alert_id               TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  rule_id                TEXT NOT NULL DEFAULT '',
  fingerprint            TEXT NOT NULL DEFAULT '',
  category               TEXT NOT NULL DEFAULT 'SYSTEM',
  severity               TEXT NOT NULL DEFAULT 'INFO',
  status                 TEXT NOT NULL DEFAULT 'OPEN',
  title                  TEXT NOT NULL DEFAULT '',
  message                TEXT NOT NULL DEFAULT '',
  occurrence_count       INTEGER NOT NULL DEFAULT 1,
  consecutive_critical_count INTEGER NOT NULL DEFAULT 0,
  first_seen_at          TEXT NOT NULL DEFAULT '',
  last_seen_at           TEXT NOT NULL DEFAULT '',
  cooldown_until         TEXT NOT NULL DEFAULT '',
  suppressed_until       TEXT NOT NULL DEFAULT '',
  acknowledged_at        TEXT NOT NULL DEFAULT '',
  investigating_at       TEXT NOT NULL DEFAULT '',
  resolved_at            TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_monitoring@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_salert_dedup
  ON strategy_alert(strategy_code, rule_id, fingerprint);

CREATE INDEX IF NOT EXISTS idx_salert_strategy ON strategy_alert(strategy_code);

CREATE TABLE IF NOT EXISTS strategy_notification_dispatch (
  dispatch_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  alert_id               TEXT NOT NULL DEFAULT '',
  channel                TEXT NOT NULL DEFAULT 'RECORDING',
  severity               TEXT NOT NULL DEFAULT 'INFO',
  payload_json           TEXT NOT NULL DEFAULT '{}',
  dispatched_at          TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_monitoring@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_snd_strategy ON strategy_notification_dispatch(strategy_code);

CREATE TABLE IF NOT EXISTS strategy_governance_event (
  event_id               TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  event_type             TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
  severity               TEXT NOT NULL DEFAULT 'CRITICAL',
  category               TEXT NOT NULL DEFAULT 'SYSTEM',
  alert_id               TEXT NOT NULL DEFAULT '',
  message                TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_strategy_monitoring@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sge_strategy ON strategy_governance_event(strategy_code);
