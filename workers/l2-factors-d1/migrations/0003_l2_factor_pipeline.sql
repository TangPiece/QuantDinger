-- L2 百因子并行链路：仅元数据。数值宽表在本地/R2 Parquet，不写入本库热值表。

CREATE TABLE IF NOT EXISTS l2_factor_definitions (
  factor_id TEXT PRIMARY KEY,
  factor_name TEXT NOT NULL,
  display_name TEXT,
  category TEXT NOT NULL,
  description TEXT,
  formula TEXT,
  input_fields TEXT,
  frequency TEXT NOT NULL DEFAULT 'day',
  factor_version INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS l2_factor_jobs (
  job_id TEXT PRIMARY KEY,
  factor_group TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  status TEXT NOT NULL,
  rows_processed INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_l2_factor_jobs_group_dates
  ON l2_factor_jobs (factor_group, start_date, end_date);

CREATE TABLE IF NOT EXISTS l2_factor_datasets (
  dataset_id TEXT PRIMARY KEY,
  factor_group TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  source_version TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  storage_uri TEXT NOT NULL,
  schema_hash TEXT NOT NULL,
  row_count INTEGER,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_l2_factor_datasets_group_dates
  ON l2_factor_datasets (factor_group, start_date, end_date);

CREATE TABLE IF NOT EXISTS l2_factor_day_status (
  trade_date TEXT NOT NULL,
  factor_group TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  source_version TEXT NOT NULL,
  status TEXT NOT NULL,
  symbol_ok INTEGER DEFAULT 0,
  symbol_fail INTEGER DEFAULT 0,
  schema_hash TEXT,
  error_message TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (trade_date, factor_group, factor_version)
);

CREATE INDEX IF NOT EXISTS idx_l2_factor_day_status_status
  ON l2_factor_day_status (status, trade_date);
