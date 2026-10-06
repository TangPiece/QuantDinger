# Phase 6D — OMS / Order Lifecycle

## Goal

Accept research **OrderIntent** (from 6C), materialize executable **Order** with
Version / Event / Fill, drive a state machine (incl. **UNKNOWN**), Outbox +
**Paper Broker** only, and write **PositionEvent** back to 6B.

Engine version: `qd_oms@1`.

## Pipeline

```text
RiskEvaluateResult.order_intents (6C)
  → OMS.accept / submit
  → Order (+ OrderVersion + OrderEvent)
  → Outbox
  → PaperBroker (PAPER only)
  → ExecutionReport → Fill
  → PositionEvent (FREEZE → BUY/SELL_FILLED)
  → Portfolio Reducer (6B)
  → STOP（不接真实 Broker；不写 pending_orders）
```

## API

```python
OMSService(store, registry, *, portfolio_service=None, paper_broker=None)

.submit_intents(
    intents, *,
    account_id, portfolio_id,
    risk_run_id="", policy_hash="",
    environment="PAPER",  # PAPER only in 6D
    metadata=None, prices=None,
) -> SubmitResult

.cancel(order_id, *, reason="") -> Order
.replace(order_id, *, quantity=None, limit_price=None) -> Order
.get_order / list_orders / list_fills / list_events
.drain_outbox(*, limit=100) -> int
```

## Status machine

```text
CREATED | VALIDATED | SUBMITTED | ACKNOWLEDGED |
PARTIALLY_FILLED | FILLED |
CANCEL_PENDING | CANCELLED |
REPLACE_PENDING | REPLACED |
REJECTED | BROKER_REJECTED | UNKNOWN
```

Illegal transitions raise `StateMachineError`.

## Principles

1. **OrderIntent ≠ Order** — 6C emits intent; OMS chooses type/TIF/price.
2. **State machine authority** — `current_status` from OrderEvent; amend via Version.
3. **Fill is fact** — `filled_quantity` / `avg_fill_price` are derived.
4. **Idempotency** — same `idempotency_key` → one logical Order.
5. **UNKNOWN** — timeout/network inject → UNKNOWN (not FAILED).
6. **No re-risk** — OMS Validation is schema/session/lot/tick only.

## Storage

- D1: [`workers/qd-research-d1/migrations/0019_oms.sql`](../../../workers/qd-research-d1/migrations/0019_oms.sql)
- R2/local: `qd/production/oms/{order_id}/` — `order.json`, `events/`, `fills/`
- **Not** product PG `pending_orders`

## Paper Broker

[`paper_broker.py`](../../../backend_api_python/app/services/oms/paper_broker.py):

- Default instant full fill @ last / limit
- Metadata inject: `partial_fills`, `reject`, `timeout_unknown`, `latency_ms` stub
- No exchange HTTP / `DataSourceFactory`

## Upstream recommendation

```text
6B SHADOW_DRY → 6C evaluate → 6D submit_intents
```

Prefer this over 6B in-process `PAPER_FILL` for production paper path.

## Non-goals

```text
❌ Real Broker / LIVE / pending_orders
❌ TWAP/VWAP/POV / Parent-Child
❌ Full reconciliation (6F)
❌ Merge Strategy V2 LiveSession
❌ Broker order id as source of truth before ACK
```

## Compatibility

- 6C API unchanged; OMS consumes `order_intents` + `risk_run_id` / `policy_hash`
- 6B `FREEZE` / filled events used by OMS fill bridge
- 6E reserved: `broker_order_id`, Outbox `BROKER_SUBMIT`

## Verify

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6d_oms.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6d_oms.py -q \
  --confcutdir=tests/research_data
```
