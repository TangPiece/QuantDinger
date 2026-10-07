# Phase 7C — Single Real Order (Controlled Live)

## 目标

在 `LIVE_CONTROLLED` 下允许 **恰好一笔** 真实 Broker **LIMIT** submit；Strategy 永不直连 Broker。

```text
Real MD → Strategy → Risk → OrderIntent
  → ControlledLiveGate → OrderExecutionGateway.submit_real
  → AlpacaControlledLiveAdapter → POST /v2/orders
  → ExecutionReport → Recon + Shadow vs Real
```

## 边界（锁死）

**做**

- 环境：`LIVE_READONLY → LIVE_CONTROLLED`（需 `PRODUCTION_READY` + operator approval）
- `max_orders=1`；timeout/UNKNOWN 仅 `GET by_client_order_id`，禁止 resubmit
- cancel/replace 硬拒；MARKET 拒
- Lineage metadata + D1 `0028` + R2 `qd/production/controlled_live/...`
- CI 默认 `FakeControlledLiveAdapter`；真实 POST 需 `CONTROLLED_LIVE_ALLOW_REAL_SUBMIT=true` + `ALPACA_LIVE_*`

**不做（Non-goals）**

```text
❌ LIVE environment
❌ Auto cancel/replace
❌ Market order first trade
❌ Resubmit on timeout
❌ Multi-order / multi-strategy scale
❌ Secrets in git / D1 / audit plaintext
```

## 包

| 路径 | 职责 |
|------|------|
| `controlled_live/` | Gate、Session、Runner、lineage、compare |
| `broker_adapter/adapters/alpaca/live_trading_transport.py` | POST + GET only |
| `broker_adapter/adapters/alpaca/controlled_live_adapter.py` | `broker_id=alpaca_live_controlled` |

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7c_controlled_live.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7c_controlled_live.py -q \
  --confcutdir=tests/research_data
```
