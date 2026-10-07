-- Phase 8A：Strategy Registry（身份 + 版本钉扎 + Policy 绑定）

CREATE TABLE IF NOT EXISTS strategy_registry (
  strategy_code   TEXT NOT NULL PRIMARY KEY,
  display_name    TEXT NOT NULL DEFAULT '',
  owner           TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'ACTIVE',
  active_version  TEXT NOT NULL DEFAULT '',
  engine_version  TEXT NOT NULL DEFAULT 'qd_strategy_registry@1',
  created_at      TEXT NOT NULL DEFAULT '',
  metadata_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS strategy_version_binding (
  version_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code         TEXT NOT NULL,
  strategy_version      TEXT NOT NULL,
  dataset_hash          TEXT NOT NULL DEFAULT '',
  snapshot_id           TEXT NOT NULL DEFAULT '',
  model_version         TEXT NOT NULL DEFAULT '',
  model_artifact_id     TEXT NOT NULL DEFAULT '',
  feature_version       TEXT NOT NULL DEFAULT '',
  processor_version     TEXT NOT NULL DEFAULT '',
  processor_hash        TEXT NOT NULL DEFAULT '',
  strategy_hash         TEXT NOT NULL DEFAULT '',
  bundle_hash           TEXT NOT NULL DEFAULT '',
  risk_policy_ref       TEXT NOT NULL DEFAULT '',
  execution_policy_ref  TEXT NOT NULL DEFAULT 'NEXT_OPEN',
  content_hash          TEXT NOT NULL DEFAULT '',
  source                TEXT NOT NULL DEFAULT 'MANUAL',
  registered_at         TEXT NOT NULL DEFAULT '',
  storage_uri           TEXT NOT NULL DEFAULT '',
  engine_version        TEXT NOT NULL DEFAULT 'qd_strategy_registry@1',
  metadata_json         TEXT NOT NULL DEFAULT '{}',
  UNIQUE (strategy_code, strategy_version)
);

CREATE INDEX IF NOT EXISTS idx_svb_strategy_hash ON strategy_version_binding(strategy_hash);
CREATE INDEX IF NOT EXISTS idx_svb_bundle_hash ON strategy_version_binding(bundle_hash);
