import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { MAX_BATCH_STATEMENTS, validateBatch, validateSql } from "../src/sql_guard.js";

describe("validateSql", () => {
  it("允许 SELECT/INSERT/CREATE", () => {
    assert.equal(validateSql("SELECT 1").ok, true);
    assert.equal(validateSql("INSERT INTO t VALUES (1)").ok, true);
    assert.equal(validateSql("CREATE TABLE IF NOT EXISTS t (id INT)").ok, true);
  });

  it("只允许给因子表加列", () => {
    assert.equal(
      validateSql("ALTER TABLE l2_factors ADD COLUMN IF NOT EXISTS l2_ofi REAL").ok,
      true,
    );
    assert.equal(validateSql("ALTER TABLE l2_factors DROP COLUMN l2_ofi").ok, false);
  });

  it("拒绝多语句与 pragma", () => {
    assert.equal(validateSql("SELECT 1; DROP TABLE t").ok, false);
    assert.equal(validateSql("PRAGMA table_info(t)").ok, false);
    assert.equal(validateSql("DROP TABLE t").ok, false);
  });
});

describe("validateBatch", () => {
  it("拒绝超限", () => {
    const statements = Array.from({ length: MAX_BATCH_STATEMENTS + 1 }, () => ({
      sql: "SELECT 1",
      params: [],
    }));
    assert.equal(validateBatch(statements).ok, false);
  });

  it("规范化合法 batch", () => {
    const result = validateBatch([{ sql: "SELECT 1;", params: [1] }]);
    assert.equal(result.ok, true);
    assert.equal(result.statements[0].sql, "SELECT 1");
  });
});
