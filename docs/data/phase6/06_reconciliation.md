# Phase 6F — Reconciliation / Execution Reconciliation

## Goal

Answer: **what QuantDinger thinks happened vs what the Broker actually did**.

Engine version: `qd_reconciliation@1`.

6F is an **observer** — Findings never overwrite OMS/Position state and never
auto-place corrective orders.

```text
OMS / Portfolio (internal)
        ↓
Reconciliation Engine
        ↑
BrokerSnapshot (via BrokerAdapter.get_*)
```

## Pipeline

```text
BrokerAdapter.get_account / get_positions / get_open_orders + executions
       ↓
BrokerSnapshot (normalized; compare must not parse Alpaca/Binance JSON)
       ↓
compare Order / Fill / Position / Cash / P&L
       ↓
ReconciliationFinding (+ ReconciliationRun)
       ↓
CRITICAL OPEN → TradingGate.block_new_orders
       ↓
OMS submit_intents rejected; cancel / recover / query still allowed
```

## API

```python
ReconciliationService(store, registry, *,
    portfolio_service, oms_service, broker_adapter_service)

.run(account_id, portfolio_id, *, mode="FAST"|"SLOW"|"EOD") -> ReconciliationRun
.list_findings(run_id=None, account_id=None, status=None)
.acknowledge / investigate / resolve / waive(finding_id)  # CRITICAL waive → FindingsError
.refresh_and_retry(account_id, portfolio_id)  # snapshot refresh only; no orders
.is_trading_blocked(account_id) -> bool

ReconciliationService(..., safety_service=safety)  # CRITICAL → Safety
OMSService.set_trading_gate(safety.gate)  # 6G authoritative (not recon.gate)
```

## Finding types (P0)

`ORDER_MISMATCH`, `FILL_MISMATCH`, `POSITION_MISMATCH`, `CASH_MISMATCH`,
`PNL_MISMATCH`, `UNEXPECTED_ORDER`, `UNEXPECTED_FILL`, `MISSING_ORDER`,
`MISSING_FILL`.

**Severity:** INFO / WARNING / ERROR / CRITICAL  
- Position `|Δqty| ≥ threshold` → ERROR/CRITICAL  
- `UNEXPECTED_ORDER` / `UNEXPECTED_FILL` → CRITICAL  
- P&L within tolerance → INFO  

**Lifecycle:** `OPEN → ACKNOWLEDGED → INVESTIGATING → RESOLVED | WAIVED`  
**CRITICAL cannot be Waived.**

## Trading Gate

CRITICAL OPEN Finding → 6F `GateState.block_new_orders` + Account
`RECONCILIATION_REQUIRED` (6B), and **`SafetyService.report_source(RECONCILIATION_CRITICAL)`**
when `ReconciliationService(..., safety_service=...)` is wired (6G OMS gate).  
All CRITICAL resolved → clear 6F gate + restore `ACTIVE` + clear Safety recon source.

## Storage

- D1: [`workers/qd-research-d1/migrations/0021_reconciliation.sql`](../../../workers/qd-research-d1/migrations/0021_reconciliation.sql)
- R2/local: `qd/production/reconciliation/{broker_id}/{account_id}/{yyyy}/{mm}/{dd}/{snapshot_id}.json`

## Simulated fault injection

Metadata / `run(..., inject=...)`:

- `force_broker_position` / `force_broker_cash`
- `drop_execution_from_snapshot` / `drop_execution_ids`
- `inject_open_orders` / `inject_executions`

Simulated fills update `_positions` / `_cash` so Snapshot can MATCH 6B.

## Non-goals

```text
❌ Auto-fix by placing orders / Emergency Flatten (→ 6G)
❌ Auto-waive CRITICAL
❌ Multi-Broker / Live funded trading
❌ Merge live_trading reconciliation
❌ Full Kill Switch suite (→ 6G)
```

## Verify

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6f_reconciliation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6f_reconciliation.py -q \
  --confcutdir=tests/research_data
```
