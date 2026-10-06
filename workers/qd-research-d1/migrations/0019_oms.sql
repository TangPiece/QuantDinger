-- Phase 6D：OMS Registry（明细在 R2；不写 pending_orders）

CREATE TABLE IF NOT EXISTS oms_order (
  order_id          TEXT NOT NULL PRIMARY KEY,
  client_order_id   TEXT NOT NULL UNIQUE,
  broker_order_id   TEXT NOT NULL DEFAULT '',
  account_id        TEXT NOT NULL DEFAULT '',
  portfolio_id      TEXT NOT NULL DEFAULT '',
  risk_run_id       TEXT NOT NULL DEFAULT '',
  policy_hash       TEXT NOT NULL DEFAULT '',
  instrument_key    TEXT NOT NULL DEFAULT '',
  side              TEXT NOT NULL DEFAULT 'BUY',
  order_type        TEXT NOT NULL DEFAULT 'MARKET',
  tif               TEXT NOT NULL DEFAULT 'DAY',
  quantity          REAL NOT NULL DEFAULT 0,
  limit_price       REAL,
  filled_quantity   REAL NOT NULL DEFAULT 0,
  avg_fill_price    REAL NOT NULL DEFAULT 0,
  status            TEXT NOT NULL DEFAULT 'CREATED',
  version           INTEGER NOT NULL DEFAULT 1,
  idempotency_key   TEXT NOT NULL UNIQUE,
  trading_date      TEXT NOT NULL DEFAULT '',
  engine_version    TEXT NOT NULL DEFAULT 'qd_oms@1',
  storage_uri       TEXT NOT NULL DEFAULT '',
  created_at        TEXT NOT NULL,
  metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_oms_o_account
  ON oms_order (account_id);

CREATE INDEX IF NOT EXISTS idx_oms_o_status
  ON oms_order (status);

CREATE TABLE IF NOT EXISTS oms_order_version (
  order_id       TEXT NOT NULL,
  version        INTEGER NOT NULL,
  quantity       REAL NOT NULL DEFAULT 0,
  limit_price    REAL,
  status         TEXT NOT NULL DEFAULT '',
  created_at     TEXT NOT NULL,
  metadata_json  TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (order_id, version)
);

CREATE TABLE IF NOT EXISTS oms_order_event (
  event_id         TEXT NOT NULL PRIMARY KEY,
  order_id         TEXT NOT NULL,
  event_type       TEXT NOT NULL,
  previous_status  TEXT NOT NULL DEFAULT '',
  new_status       TEXT NOT NULL DEFAULT '',
  source           TEXT NOT NULL DEFAULT 'OMS',
  message          TEXT NOT NULL DEFAULT '',
  payload_json     TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oms_oe_order
  ON oms_order_event (order_id);

CREATE TABLE IF NOT EXISTS oms_fill (
  fill_id          TEXT NOT NULL PRIMARY KEY,
  order_id         TEXT NOT NULL,
  instrument_key   TEXT NOT NULL DEFAULT '',
  side             TEXT NOT NULL DEFAULT 'BUY',
  quantity         REAL NOT NULL DEFAULT 0,
  price            REAL NOT NULL DEFAULT 0,
  fee              REAL NOT NULL DEFAULT 0,
  trading_date     TEXT NOT NULL DEFAULT '',
  created_at       TEXT NOT NULL,
  metadata_json    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_oms_f_order
  ON oms_fill (order_id);

CREATE TABLE IF NOT EXISTS oms_cancel_request (
  request_id    TEXT NOT NULL PRIMARY KEY,
  order_id      TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'PENDING',
  reason        TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS oms_replace_request (
  request_id    TEXT NOT NULL PRIMARY KEY,
  order_id      TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'PENDING',
  quantity      REAL,
  limit_price   REAL,
  created_at    TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS oms_outbox (
  outbox_id       TEXT NOT NULL PRIMARY KEY,
  aggregate_type  TEXT NOT NULL DEFAULT 'ORDER',
  aggregate_id    TEXT NOT NULL DEFAULT '',
  event_type      TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'PENDING',
  payload_json    TEXT NOT NULL DEFAULT '{}',
  created_at      TEXT NOT NULL,
  sent_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_oms_ob_status
  ON oms_outbox (status);
