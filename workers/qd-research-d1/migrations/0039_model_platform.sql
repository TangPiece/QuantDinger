-- Phase 9F-1：Model Platform schema lock（additive；runtime SSOT 仍可为 LocalJson）

-- Model 扩展：类型 / framework / owner / status / 平台 id
ALTER TABLE model ADD COLUMN platform_model_id TEXT;
ALTER TABLE model ADD COLUMN model_type TEXT NOT NULL DEFAULT 'CUSTOM';
ALTER TABLE model ADD COLUMN framework TEXT;
ALTER TABLE model ADD COLUMN owner TEXT;
ALTER TABLE model ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE model ADD COLUMN description TEXT;
ALTER TABLE model ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE model ADD COLUMN updated_at TEXT;
ALTER TABLE model ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}';

-- ModelVersion 扩展：lifecycle + lineage hashes
ALTER TABLE model_version ADD COLUMN platform_model_version_id TEXT;
ALTER TABLE model_version ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'DRAFT';
ALTER TABLE model_version ADD COLUMN version_content_hash TEXT;
ALTER TABLE model_version ADD COLUMN dataset_hash TEXT;
ALTER TABLE model_version ADD COLUMN snapshot_id TEXT;
ALTER TABLE model_version ADD COLUMN feature_set_id TEXT;
ALTER TABLE model_version ADD COLUMN feature_set_hash TEXT;
ALTER TABLE model_version ADD COLUMN factor_portfolio_id TEXT;
ALTER TABLE model_version ADD COLUMN factor_portfolio_version TEXT;
ALTER TABLE model_version ADD COLUMN label_id TEXT;
ALTER TABLE model_version ADD COLUMN label_hash TEXT;
ALTER TABLE model_version ADD COLUMN processor_version TEXT;
ALTER TABLE model_version ADD COLUMN model_config_hash TEXT;
ALTER TABLE model_version ADD COLUMN hyperparameter_hash TEXT;
ALTER TABLE model_version ADD COLUMN framework TEXT;
ALTER TABLE model_version ADD COLUMN framework_version TEXT;
ALTER TABLE model_version ADD COLUMN code_version TEXT;
ALTER TABLE model_version ADD COLUMN environment_hash TEXT;
ALTER TABLE model_version ADD COLUMN random_seed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE model_version ADD COLUMN training_run_id TEXT;
ALTER TABLE model_version ADD COLUMN deprecate_reason TEXT;
ALTER TABLE model_version ADD COLUMN replacement_ref TEXT;
ALTER TABLE model_version ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE model_version ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_model_platform_model_id
  ON model (platform_model_id);

CREATE INDEX IF NOT EXISTS idx_model_version_platform_id
  ON model_version (platform_model_version_id);

CREATE INDEX IF NOT EXISTS idx_model_version_lifecycle
  ON model_version (lifecycle);

-- TrainingRun（不可变过程记录）
CREATE TABLE IF NOT EXISTS training_run (
  training_run_id        TEXT PRIMARY KEY,
  training_run_hash      TEXT NOT NULL,
  model_id               INTEGER REFERENCES model(model_id),
  platform_model_id      TEXT,
  model_code             TEXT,
  model_version_id       INTEGER REFERENCES model_version(model_version_id),
  platform_model_version_id TEXT,
  dataset_hash           TEXT,
  feature_set_hash       TEXT,
  factor_portfolio_hash  TEXT,
  train_start            TEXT,
  train_end              TEXT,
  validation_start       TEXT,
  validation_end         TEXT,
  random_seed            INTEGER NOT NULL DEFAULT 0,
  hyperparameters_json   TEXT NOT NULL DEFAULT '{}',
  resource_config_json   TEXT NOT NULL DEFAULT '{}',
  status                 TEXT NOT NULL,
  started_at             TEXT,
  finished_at            TEXT,
  logs_uri               TEXT,
  metrics_uri            TEXT,
  immutable              INTEGER NOT NULL DEFAULT 1,
  created_at             TEXT NOT NULL,
  metadata_json          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_training_run_hash
  ON training_run (training_run_hash);

CREATE INDEX IF NOT EXISTS idx_training_run_model
  ON training_run (platform_model_id);

-- ModelArtifact 自描述索引扩展（复用 artifact 表）
ALTER TABLE artifact ADD COLUMN model_version_id INTEGER REFERENCES model_version(model_version_id);
ALTER TABLE artifact ADD COLUMN platform_model_version_id TEXT;
ALTER TABLE artifact ADD COLUMN framework TEXT;
ALTER TABLE artifact ADD COLUMN framework_version TEXT;
ALTER TABLE artifact ADD COLUMN feature_schema_uri TEXT;
ALTER TABLE artifact ADD COLUMN processor_uri TEXT;
ALTER TABLE artifact ADD COLUMN label_definition_uri TEXT;
ALTER TABLE artifact ADD COLUMN environment_uri TEXT;
ALTER TABLE artifact ADD COLUMN training_metadata_uri TEXT;
