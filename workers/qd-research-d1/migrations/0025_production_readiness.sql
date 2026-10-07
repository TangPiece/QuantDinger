-- Phase 6J：Production Readiness（大 payload 在 R2）

CREATE TABLE IF NOT EXISTS readiness_run (
  run_id              TEXT NOT NULL PRIMARY KEY,
  production_ready    INTEGER NOT NULL DEFAULT 0,
  engine_version      TEXT NOT NULL DEFAULT 'qd_readiness@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS readiness_check_result (
  check_result_id     TEXT NOT NULL PRIMARY KEY,
  run_id              TEXT NOT NULL DEFAULT '',
  check_id            TEXT NOT NULL DEFAULT '',
  scenario_id         TEXT NOT NULL DEFAULT '',
  status              TEXT NOT NULL DEFAULT 'OK',
  title               TEXT NOT NULL DEFAULT '',
  engine_version      TEXT NOT NULL DEFAULT 'qd_readiness@1',
  metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_readiness_check_run
  ON readiness_check_result (run_id);
