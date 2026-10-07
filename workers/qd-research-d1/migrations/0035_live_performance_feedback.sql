-- Phase 8E：Live Performance Feedback（观察记录，非自动降级）

CREATE TABLE IF NOT EXISTS drift_policy (
  policy_id              TEXT NOT NULL,
  policy_version         TEXT NOT NULL,
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  rules_json             TEXT NOT NULL DEFAULT '[]',
  engine_version         TEXT NOT NULL DEFAULT 'qd_live_performance_feedback@1',
  description            TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (policy_id, policy_version)
);

CREATE TABLE IF NOT EXISTS performance_expected_baseline (
  baseline_id            TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  strategy_version       TEXT NOT NULL DEFAULT '',
  content_hash           TEXT NOT NULL DEFAULT '',
  candidate_id           TEXT NOT NULL DEFAULT '',
  validation_id          TEXT NOT NULL DEFAULT '',
  pipeline_run_id        TEXT NOT NULL DEFAULT '',
  dataset_hash           TEXT NOT NULL DEFAULT '',
  snapshot_id            TEXT NOT NULL DEFAULT '',
  model_version          TEXT NOT NULL DEFAULT '',
  feature_version        TEXT NOT NULL DEFAULT '',
  backtest_hash          TEXT NOT NULL DEFAULT '',
  baseline_type          TEXT NOT NULL DEFAULT 'PROMOTION_BASELINE',
  metrics_snapshot_json  TEXT NOT NULL DEFAULT '{}',
  drift_policy_id        TEXT NOT NULL DEFAULT '',
  drift_policy_version   TEXT NOT NULL DEFAULT '',
  drift_policy_content_hash TEXT NOT NULL DEFAULT '',
  immutable              INTEGER NOT NULL DEFAULT 1,
  created_at             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_live_performance_feedback@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_peb_promotion
  ON performance_expected_baseline(pipeline_run_id);

CREATE INDEX IF NOT EXISTS idx_peb_strategy ON performance_expected_baseline(strategy_code);

CREATE TABLE IF NOT EXISTS performance_comparison_run (
  run_id                 TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  baseline_id            TEXT NOT NULL,
  actual_source          TEXT NOT NULL DEFAULT 'SHADOW',
  window_start           TEXT NOT NULL DEFAULT '',
  window_end             TEXT NOT NULL DEFAULT '',
  idempotency_key        TEXT NOT NULL DEFAULT '',
  status                 TEXT NOT NULL DEFAULT 'CREATED',
  policy_id              TEXT NOT NULL DEFAULT '',
  policy_version         TEXT NOT NULL DEFAULT '',
  policy_content_hash    TEXT NOT NULL DEFAULT '',
  actual_metrics_json    TEXT NOT NULL DEFAULT '{}',
  deviation_json         TEXT NOT NULL DEFAULT '{}',
  drift_findings_json    TEXT NOT NULL DEFAULT '[]',
  report_id              TEXT NOT NULL DEFAULT '',
  started_at             TEXT NOT NULL DEFAULT '',
  completed_at           TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_live_performance_feedback@1',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pcr_idempotency
  ON performance_comparison_run(baseline_id, idempotency_key);

CREATE INDEX IF NOT EXISTS idx_pcr_strategy ON performance_comparison_run(strategy_code);
CREATE INDEX IF NOT EXISTS idx_pcr_baseline ON performance_comparison_run(baseline_id);
