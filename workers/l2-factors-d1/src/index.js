/**
 * Level2 因子 D1 代理 Worker。
 * Python 后端带 Bearer Token 调用 /v1/query 与 /v1/batch，经 binding 访问 D1。
 */
import { MAX_BATCH_STATEMENTS, validateBatch, validateSql } from "./sql_guard.js";

/**
 * @param {Request} request
 * @param {{ DB: D1Database, WORKER_TOKEN: string }} env
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, service: "l2-factors-d1" });
    }
    if (request.method !== "POST") {
      return json({ ok: false, error: "只支持 POST" }, 405);
    }
    if (!authorize(request, env)) {
      return json({ ok: false, error: "unauthorized" }, 401);
    }
    if (!env.DB) {
      return json({ ok: false, error: "D1 binding 未配置" }, 500);
    }
    try {
      if (url.pathname === "/v1/query") {
        return await handleQuery(request, env);
      }
      if (url.pathname === "/v1/batch") {
        return await handleBatch(request, env);
      }
      return json({ ok: false, error: "not found" }, 404);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return json({ ok: false, error: message }, 500);
    }
  },
};

/**
 * @param {Request} request
 * @param {{ WORKER_TOKEN?: string }} env
 */
function authorize(request, env) {
  const expected = String(env.WORKER_TOKEN || "").trim();
  if (!expected) {
    return false;
  }
  const header = request.headers.get("Authorization") || "";
  const match = /^Bearer\s+(.+)$/i.exec(header);
  if (!match) {
    return false;
  }
  return timingSafeEqual(match[1].trim(), expected);
}

/** 简单常量时间比较，避免 Token 长度泄露到日志以外的旁路。 */
function timingSafeEqual(a, b) {
  if (a.length !== b.length) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

/**
 * @param {Request} request
 * @param {{ DB: D1Database }} env
 */
async function handleQuery(request, env) {
  const body = await request.json();
  const sql = body?.sql;
  const check = validateSql(sql);
  if (!check.ok) {
    return json({ ok: false, error: check.error }, 400);
  }
  const params = Array.isArray(body?.params) ? body.params : [];
  const cleaned = String(sql).trim().replace(/;\s*$/, "");
  const stmt = env.DB.prepare(cleaned).bind(...params);
  // 读用 all，写（无结果集）用 run，统一包进 results。
  const isSelect = cleaned.trim().toUpperCase().startsWith("SELECT");
  if (isSelect) {
    const result = await stmt.all();
    return json({ ok: true, results: [result] });
  }
  const result = await stmt.run();
  return json({ ok: true, results: [result] });
}

/**
 * @param {Request} request
 * @param {{ DB: D1Database }} env
 */
async function handleBatch(request, env) {
  const body = await request.json();
  const check = validateBatch(body?.statements);
  if (!check.ok) {
    return json({ ok: false, error: check.error }, 400);
  }
  const prepared = check.statements.map((item) =>
    env.DB.prepare(item.sql).bind(...item.params),
  );
  const results = await env.DB.batch(prepared);
  return json({
    ok: true,
    results,
    meta: { max_batch_statements: MAX_BATCH_STATEMENTS },
  });
}

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}
