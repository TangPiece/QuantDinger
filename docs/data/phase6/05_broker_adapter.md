# Phase 6E — Broker Adapter

## Goal

Validate the **BrokerAdapter Contract** and OMS closed loop — **not** exchange
feature coverage.

Engine version: `qd_broker_adapter@1`.

**Reference Adapter = Alpaca Paper** (Paper only; no Live).

Existing `live_trading` already answers “how to trade”. 6E answers “how QuantDinger
Domain connects to any broker without being polluted by broker-specific status”.

## Pipeline

```text
6C OrderIntent → 6D OMS
       ↓ Outbox (PAPER_SUBMIT | BROKER_SUBMIT)
BrokerAdapter Contract
  ├─ PaperBrokerAdapter (+ Fake REST/WS SimulatedBroker)   ← P0
  └─ AlpacaPaperAdapter → Alpaca Paper API only            ← P1
       ↓
ExecutionReport
       ↓
6D reducer → Fill → 6B Position
STOP：无 LIVE；无 Multi-Broker；不写 pending_orders；不合并 live_trading Domain
```

## API

```python
BrokerAdapterService(store, registry, *, adapter=None, execution_mode="PAPER")

.connect() / .disconnect() / .health()
.submit_order(order) -> ExecutionReport
.start_event_pump(callback) -> int
.recover_order(order) -> ExecutionReport  # UNKNOWN → query；禁止自动重下单

OMSService(..., broker_port=adapter, broker_adapter_service=svc)
.submit_intents(..., environment="PAPER|SANDBOX|SHADOW")
.drain_outbox()          # PAPER_SUBMIT | BROKER_SUBMIT
.recover_unknown_order(order_id)
```

## Principles

1. OMS / Reducer only see `ExecutionReport` — never `if broker.status == "NEW"`.
2. `live_trading` / `alpaca_trading` are **read-only references**; adapters are
   independent. Pure transport may be copied; Domain place-order paths must not.
3. Credentials from env only (`ALPACA_PAPER_*`); never D1/R2/Order.metadata/logs.
4. `LIVE` / Alpaca Live hosts → hard reject.
5. Event dedup: `unique(broker_id, broker_execution_id)`.
6. Raw events on R2/local; D1 keeps `broker_event_index` only.

## execution_mode

| Mode | Adapter |
|------|---------|
| `PAPER` | PaperBrokerAdapter → `oms.PaperBroker` |
| `SANDBOX` / `SHADOW` | SimulatedBroker (Fake REST/WS) |
| `ALPACA_PAPER` | AlpacaPaperAdapter (Paper API only) |
| `LIVE` | Forbidden |

## Storage

- D1: [`workers/qd-research-d1/migrations/0020_broker_adapter.sql`](../../../workers/qd-research-d1/migrations/0020_broker_adapter.sql)
- R2/local: `qd/production/broker/{broker_id}/events/{yyyy}/{mm}/{dd}/`

## Non-goals

```text
❌ Binance / OKX / IBKR Adapter
❌ Multi-Broker Routing / SOR / Failover
❌ Alpaca Live / any LIVE funded trading
❌ Merge live_trading Domain (OMS / strategy / account state machine)
❌ Full Reconciliation (→ 6F)
❌ Parent/Child / TWAP/VWAP
```

## Compatibility

- 6D OMS extended: `BrokerPort`, `BROKER_SUBMIT`, `recover_unknown_order`,
  `environment=SANDBOX|SHADOW`; Paper sync path unchanged for 6D tests
- 6F reserved: Broker Position/Account views for reconciliation (`0021_…`)

## Verify

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6e_broker_adapter.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6e_broker_adapter.py -q \
  --confcutdir=tests/research_data
```
