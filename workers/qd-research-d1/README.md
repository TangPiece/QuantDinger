# qd-research-d1

研究 Registry（`qd_research`）的 Cloudflare Worker + D1 代理。QuantDinger Python 后端通过 HTTP 调用本服务，不直连 D1 REST。

与 [`l2-factors-d1`](../l2-factors-d1/) **独立**：不读写 `l2_factors`，不存行情事实数据。

## 部署

```bash
cd workers/qd-research-d1
npm install
npx wrangler d1 create qd_research
# 把返回的 database_id 写入 wrangler.toml
npx wrangler d1 migrations apply qd_research --remote
echo -n '<随机 token>' | npx wrangler secret put WORKER_TOKEN
npx wrangler deploy
```

把 Worker URL 与同一 token 写入 `backend_api_python/.env`：

```
D1_RESEARCH_WORKER_URL=https://qd-research-d1.<account>.workers.dev
D1_RESEARCH_WORKER_TOKEN=<随机 token>
```

勿与 Level2 的 `D1_WORKER_URL` / `D1_WORKER_TOKEN` 混用。

## 接口

- `GET /health`：探活
- `POST /v1/query`：`{ "sql", "params" }`，需 `Authorization: Bearer ...`
- `POST /v1/batch`：`{ "statements": [{ "sql", "params" }] }`，单次最多 200 条

## 本地测试

```bash
npm test
```
