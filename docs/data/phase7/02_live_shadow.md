# Phase 7B — Live Market Data + Shadow Trading

## 目标

真实行情 + 策略/风控/订单意图在生产 Domain 跑通，**订单永远停在 Shadow**，真实 `submit/cancel/replace` 调用次数 = **0**。

```text
Live MD → MarketEvent → Strategy → Risk → OrderIntent
       → Shadow OMS → Shadow Execution → Shadow Position/PnL
       ✕ Broker.submitOrder / cancel / replace
```

与 7A 并联：`LiveReadonlyAdapter` 提供真实持仓；Shadow 持仓持续对账（只观察，不补仓）。

## 包

| 包 | 职责 |
|----|------|
| `live_market_data/` | Canonical Quote/Bar/MarketEvent；Alpaca Data GET（`data.alpaca.markets`）；Fake transport 默认 CI |
| `shadow_trading/` | Shadow OMS/模拟成交/Ledger；`OrderExecutionGateway` 硬拒 REAL_BROKER |

## 环境阶梯（7B 收紧）

- `PAPER` → 仅 `SHADOW`
- `SHADOW` → `LIVE_READONLY`（需 `PRODUCTION_READY`）
- **禁止** `PAPER` → `LIVE_READONLY` 直跳
- `LIVE_CONTROLLED` / `LIVE` 仍 7C+ 拒绝

## 凭证

- Trading 只读（7A）：`ALPACA_LIVE_*` + `api.alpaca.markets`
- Data（7B）：同钥 + `ALPACA_LIVE_DATA_URL=https://data.alpaca.markets`（可选 `ALPACA_LIVE_STREAM_URL`）

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7b_shadow_trading.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7b_shadow_trading.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Real submit/cancel/replace
❌ LIVE_CONTROLLED / LIVE
❌ PAPER→LIVE or PAPER→LIVE_READONLY jump
❌ Secrets in git / D1 / audit plaintext
❌ Strategy depends on vendor Quote SDK types
```
