-- Phase 8H：Production → Research Feedback Loop（immutable artifacts）

CREATE TABLE IF NOT EXISTS production_feedback_dataset (
  dataset_id             TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  feedback_type          TEXT NOT NULL DEFAULT 'PERFORMANCE_FEEDBACK',
  dataset_hash           TEXT NOT NULL DEFAULT '',
  schema_version         TEXT NOT NULL DEFAULT 'pf_schema@1',
  filter_spec_json       TEXT NOT NULL DEFAULT '{}',
  window_start           TEXT NOT NULL DEFAULT '',
  window_end             TEXT NOT NULL DEFAULT '',
  processor_id           TEXT NOT NULL DEFAULT 'pf_processor@1',
  processor_version      TEXT NOT NULL DEFAULT '1',
  quality_gate_verdict   TEXT NOT NULL DEFAULT 'PASS',
  lineage_json           TEXT NOT NULL DEFAULT '{}',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_production_research_feedback@1',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pfd_strategy ON production_feedback_dataset(strategy_code);

CREATE TABLE IF NOT EXISTS production_reality_snapshot (
  snapshot_id            TEXT NOT NULL,
  snapshot_version       INTEGER NOT NULL DEFAULT 1,
  supersedes_snapshot_id TEXT NOT NULL DEFAULT '',
  strategy_code          TEXT NOT NULL,
  reality_kind           TEXT NOT NULL DEFAULT 'ACTUAL',
  as_of_time             TEXT NOT NULL DEFAULT '',
  pnl_total              REAL NOT NULL DEFAULT 0.0,
  metrics_json           TEXT NOT NULL DEFAULT '{}',
  dataset_id             TEXT NOT NULL DEFAULT '',
  content_hash           TEXT NOT NULL DEFAULT '',
  lineage_json           TEXT NOT NULL DEFAULT '{}',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_production_research_feedback@1',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (snapshot_id, snapshot_version)
);

CREATE INDEX IF NOT EXISTS idx_prs_strategy ON production_reality_snapshot(strategy_code);
CREATE INDEX IF NOT EXISTS idx_prs_reality ON production_reality_snapshot(reality_kind);

CREATE TABLE IF NOT EXISTS research_failure_case (
  case_id                TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  incident_id            TEXT NOT NULL DEFAULT '',
  governance_decision_id TEXT NOT NULL DEFAULT '',
  dataset_hash           TEXT NOT NULL DEFAULT '',
  feedback_dataset_id    TEXT NOT NULL DEFAULT '',
  category               TEXT NOT NULL DEFAULT 'SYSTEM',
  severity               TEXT NOT NULL DEFAULT 'CRITICAL',
  summary                TEXT NOT NULL DEFAULT '',
  lineage_json           TEXT NOT NULL DEFAULT '{}',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_production_research_feedback@1',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rfc_strategy ON research_failure_case(strategy_code);

CREATE TABLE IF NOT EXISTS research_hypothesis (
  hypothesis_id          TEXT NOT NULL PRIMARY KEY,
  strategy_code          TEXT NOT NULL,
  status                 TEXT NOT NULL DEFAULT 'DRAFT',
  failure_case_ids_json  TEXT NOT NULL DEFAULT '[]',
  feedback_dataset_id    TEXT NOT NULL DEFAULT '',
  title                  TEXT NOT NULL DEFAULT '',
  description            TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_production_research_feedback@1',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_rhyp_strategy ON research_hypothesis(strategy_code);

CREATE TABLE IF NOT EXISTS feedback_experiment_link (
  link_id                TEXT NOT NULL PRIMARY KEY,
  experiment_id          TEXT NOT NULL,
  strategy_code          TEXT NOT NULL,
  parent_feedback_dataset_id TEXT NOT NULL DEFAULT '',
  parent_failure_case_ids_json TEXT NOT NULL DEFAULT '[]',
  parent_incident_ids_json TEXT NOT NULL DEFAULT '[]',
  hypothesis_id          TEXT NOT NULL DEFAULT '',
  session_id             TEXT NOT NULL DEFAULT '',
  storage_uri            TEXT NOT NULL DEFAULT '',
  engine_version         TEXT NOT NULL DEFAULT 'qd_production_research_feedback@1',
  created_at             TEXT NOT NULL DEFAULT '',
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_fel_experiment ON feedback_experiment_link(experiment_id);
