# l2-factors-d1

Level2 日频因子的 Cloudflare Worker + D1 代理。QuantDinger Python 后端通过 HTTP 调用本服务，不直连 D1 REST。

## 部署

```bash
cd workers/l2-factors-d1
npm install
npx wrangler d1 create l2_factors
# 把返回的 database_id 写入 wrangler.toml
npx wrangler d1 migrations apply l2_factors --remote
echo -n '<随机 token>' | npx wrangler secret put WORKER_TOKEN
npx wrangler deploy
```

把 Worker URL 与同一 token 写入 `backend_api_python/.env`：

```
D1_WORKER_URL=https://l2-factors-d1.<account>.workers.dev
D1_WORKER_TOKEN=<随机 token>
```

## 接口

- `GET /health`：探活
- `POST /v1/query`：`{ "sql", "params" }`，需 `Authorization: Bearer ...`
- `POST /v1/batch`：`{ "statements": [{ "sql", "params" }] }`，单次最多 200 条
