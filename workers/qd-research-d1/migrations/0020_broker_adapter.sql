-- Phase 6E：Broker Adapter Registry（明细在 R2；不写 pending_orders）

CREATE TABLE IF NOT EXISTS broker_session (
  session_id       TEXT NOT NULL PRIMARY KEY,
  broker_id        TEXT NOT NULL DEFAULT '',
  execution_mode   TEXT NOT NULL DEFAULT 'PAPER',
  status           TEXT NOT NULL DEFAULT 'DISCONNECTED',
  engine_version   TEXT NOT NULL DEFAULT 'qd_broker_adapter@1',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_broker_sess_broker
  ON broker_session (broker_id);

CREATE TABLE IF NOT EXISTS broker_order_link (
  order_id          TEXT NOT NULL PRIMARY KEY,
  client_order_id   TEXT NOT NULL UNIQUE,
  broker_order_id   TEXT,
  broker_id         TEXT NOT NULL DEFAULT '',
  account_id        TEXT NOT NULL DEFAULT '',
  created_at        TEXT NOT NULL,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_broker_link_boid
  ON broker_order_link (broker_id, broker_order_id)
  WHERE broker_order_id IS NOT NULL AND broker_order_id != '';

CREATE TABLE IF NOT EXISTS broker_execution_dedup (
  broker_id             TEXT NOT NULL,
  broker_execution_id   TEXT NOT NULL,
  created_at            TEXT NOT NULL,
  PRIMARY KEY (broker_id, broker_execution_id)
);

CREATE TABLE IF NOT EXISTS broker_event_index (
  event_id       TEXT NOT NULL PRIMARY KEY,
  broker_id      TEXT NOT NULL DEFAULT '',
  received_at    TEXT NOT NULL,
  storage_uri    TEXT NOT NULL DEFAULT '',
  checksum       TEXT NOT NULL DEFAULT '',
  metadata_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_broker_ev_broker
  ON broker_event_index (broker_id);
