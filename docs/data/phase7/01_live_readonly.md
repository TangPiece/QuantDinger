# Phase 7A — Live Adapter & Read-only Production

## 目标

真实 Broker / 真实账户 **只读** 接入，与 6A–6J Domain 对齐：

```text
✓ Auth / Account / Balance / Positions / Orders / Executions
✓ BrokerSnapshot → Reconciliation（观察）
✗ Submit / Cancel / Replace
```

## TradingEnvironment 阶梯

```text
PAPER → SHADOW → LIVE_READONLY → LIVE_CONTROLLED → LIVE
```

7A **禁止**：

- `PAPER → LIVE` 跳跃
- 进入 `LIVE_CONTROLLED` / `LIVE`
- OMS `_ALLOWED_ENV` 增加 `LIVE`（发单仍仅 Paper/Sandbox）

## 前置门

- `PRODUCTION_READY=true`（环境变量或 Registry `readiness_run.production_ready`）
- 凭证：`ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_API_SECRET` / `ALPACA_LIVE_BASE_URL`
- Host 白名单：**仅** `https://api.alpaca.markets`

## 包结构

`backend_api_python/app/services/live_readonly/`

| 模块 | 职责 |
|------|------|
| `protocol.py` | `ENGINE_VERSION=qd_live_readonly@1`，Session/Capabilities |
| `modes.py` | 环境转换门禁 |
| `credentials.py` | `ALPACA_LIVE_*` |
| `gate.py` | `require_production_ready` |
| `transport.py` | GET-only HTTP + `FakeTransport` |
| `adapter.py` | `LiveReadonlyAdapter` 写单硬拒 |
| `runner.py` | `LiveReadonlyService`（**不**接 OMS broker_port） |

## 存储

- D1: `workers/qd-research-d1/migrations/0026_live_readonly.sql`
- R2: `qd/production/live_readonly/{account_id}/{yyyy}/{mm}/{dd}/{snapshot_id}.json`

## Non-goals（7A）

```text
❌ Live Submit / Cancel / Replace
❌ LIVE_CONTROLLED / LIVE 发单
❌ 密钥写入 git / D1 / Audit 明文
❌ 复用 ALPACA_PAPER_* 访问 Live host
```

Next: **7B Live Shadow**（真实行情 + Shadow 比较，仍不发单）。
