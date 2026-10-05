/**
 * SQL 安全校验：只允许白名单首词，拒绝多语句与危险 pragma。
 * 研究 Registry Worker 不开放 ALTER（schema 仅经 wrangler migrations）。
 */

/** 单次 batch 最多语句数，与 Python 侧切块对齐。 */
export const MAX_BATCH_STATEMENTS = 200;

const ALLOWED = new Set([
  "SELECT",
  "INSERT",
  "UPDATE",
  "DELETE",
  "CREATE",
]);

/**
 * @param {string} sql
 * @returns {{ ok: true } | { ok: false, error: string }}
 */
export function validateSql(sql) {
  if (typeof sql !== "string" || !sql.trim()) {
    return { ok: false, error: "sql 不能为空" };
  }
  const trimmed = sql.trim();
  const semi = trimmed.indexOf(";");
  if (semi >= 0 && trimmed.slice(semi + 1).trim() !== "") {
    return { ok: false, error: "不允许一条请求里拼多条 SQL" };
  }
  const body = semi >= 0 ? trimmed.slice(0, semi).trim() : trimmed;
  const upper = body.toUpperCase();
  if (upper.includes("PRAGMA") || upper.includes("ATTACH") || upper.includes("DETACH")) {
    return { ok: false, error: "不允许 pragma/attach" };
  }
  const first = upper.split(/\s+/, 1)[0];
  if (!ALLOWED.has(first)) {
    return { ok: false, error: `不允许的 SQL 首词: ${first || "(空)"}` };
  }
  return { ok: true };
}

/**
 * @param {unknown} statements
 * @returns {{ ok: true, statements: Array<{sql: string, params: unknown[]}> } | { ok: false, error: string }}
 */
export function validateBatch(statements) {
  if (!Array.isArray(statements) || statements.length === 0) {
    return { ok: false, error: "statements 必须是非空数组" };
  }
  if (statements.length > MAX_BATCH_STATEMENTS) {
    return {
      ok: false,
      error: `statements 超过上限 ${MAX_BATCH_STATEMENTS}`,
    };
  }
  const normalized = [];
  for (const item of statements) {
    if (!item || typeof item !== "object") {
      return { ok: false, error: "statements 项无效" };
    }
    const sql = item.sql;
    const check = validateSql(sql);
    if (!check.ok) {
      return check;
    }
    const params = Array.isArray(item.params) ? item.params : [];
    normalized.push({ sql: String(sql).trim().replace(/;\s*$/, ""), params });
  }
  return { ok: true, statements: normalized };
}
