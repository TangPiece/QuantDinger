-- Phase 9F-5：Model Artifact Store 字段（D1 索引；二进制仍在 R2/本地 Bundle）
-- Verify 以 LocalJson + qd/artifacts/model/{artifact_id}/ 为 SSOT。

ALTER TABLE artifact ADD COLUMN status TEXT;
ALTER TABLE artifact ADD COLUMN checksum_algorithm TEXT;
ALTER TABLE artifact ADD COLUMN content_type TEXT;
ALTER TABLE artifact ADD COLUMN producer_type TEXT;
ALTER TABLE artifact ADD COLUMN producer_id TEXT;
ALTER TABLE artifact ADD COLUMN manifest_uri TEXT;
ALTER TABLE artifact ADD COLUMN metadata_uri TEXT;
ALTER TABLE artifact ADD COLUMN immutable INTEGER;
ALTER TABLE artifact ADD COLUMN immutable_at TEXT;
