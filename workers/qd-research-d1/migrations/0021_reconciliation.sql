-- Phase 6F：Reconciliation Registry（明细 Snapshot 在 R2；不写 pending_orders）

CREATE TABLE IF NOT EXISTS reconciliation_run (
  run_id            TEXT NOT NULL PRIMARY KEY,
  account_id        TEXT NOT NULL DEFAULT '',
  portfolio_id      TEXT NOT NULL DEFAULT '',
  broker_id         TEXT NOT NULL DEFAULT '',
  mode              TEXT NOT NULL DEFAULT 'FAST',
  started_at        TEXT,
  completed_at      TEXT,
  snapshot_id       TEXT NOT NULL DEFAULT '',
  finding_count     INTEGER NOT NULL DEFAULT 0,
  critical_count    INTEGER NOT NULL DEFAULT 0,
  gate_blocked      INTEGER NOT NULL DEFAULT 0,
  engine_version    TEXT NOT NULL DEFAULT 'qd_reconciliation@1',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_recon_run_acct
  ON reconciliation_run (account_id);

CREATE TABLE IF NOT EXISTS reconciliation_finding (
  finding_id        TEXT NOT NULL PRIMARY KEY,
  run_id            TEXT NOT NULL DEFAULT '',
  type              TEXT NOT NULL DEFAULT '',
  severity          TEXT NOT NULL DEFAULT 'WARNING',
  status            TEXT NOT NULL DEFAULT 'OPEN',
  entity_type       TEXT NOT NULL DEFAULT '',
  entity_id         TEXT NOT NULL DEFAULT '',
  expected_json     TEXT NOT NULL DEFAULT '{}',
  actual_json       TEXT NOT NULL DEFAULT '{}',
  difference_json   TEXT NOT NULL DEFAULT '{}',
  detected_at       TEXT,
  resolved_at       TEXT,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_recon_find_run
  ON reconciliation_finding (run_id);
CREATE INDEX IF NOT EXISTS idx_recon_find_status
  ON reconciliation_finding (status);

CREATE TABLE IF NOT EXISTS broker_snapshot_index (
  snapshot_id       TEXT NOT NULL PRIMARY KEY,
  broker_id         TEXT NOT NULL DEFAULT '',
  account_id        TEXT NOT NULL DEFAULT '',
  captured_at       TEXT,
  storage_uri       TEXT NOT NULL DEFAULT '',
  checksum          TEXT NOT NULL DEFAULT '',
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_broker_snap_acct
  ON broker_snapshot_index (account_id);

CREATE TABLE IF NOT EXISTS reconciliation_cursor (
  account_id        TEXT NOT NULL,
  broker_id         TEXT NOT NULL DEFAULT '',
  cursor_type       TEXT NOT NULL,
  cursor_value      TEXT NOT NULL DEFAULT '',
  updated_at        TEXT NOT NULL,
  PRIMARY KEY (account_id, broker_id, cursor_type)
);

CREATE TABLE IF NOT EXISTS reconciliation_gate (
  account_id        TEXT NOT NULL PRIMARY KEY,
  blocked           INTEGER NOT NULL DEFAULT 0,
  reason            TEXT NOT NULL DEFAULT '',
  finding_id        TEXT NOT NULL DEFAULT '',
  updated_at        TEXT NOT NULL,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);
