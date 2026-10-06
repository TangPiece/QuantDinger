# Phase 6G — Trading Safety / Kill Switch

## Goal

Answer: **should this order be allowed to leave OMS?** (6F only checks consistency.)

Engine version: `qd_safety@1`.

6G is the **last Fail-Closed gate** before `submit_intents`. It does not create orders,
mutate positions, or replace the 6C Risk Engine.

```text
OrderIntent → Risk (6C) → Safety (6G) → OMS → BrokerAdapter
Reconciliation CRITICAL ──report_source──► Safety
```

## Decisions

```text
ALLOW | BLOCK_NEW_ORDER | HALT | EMERGENCY
```

Action **intents** only (P0 does not execute): `CANCEL_OPEN_ORDERS`, `FLATTEN_ALL`.

## Fail-Closed

- `SafetyState.UNKNOWN` or `safety_state_known=False` → `BLOCK_NEW_ORDER`
- Safety evaluate / gate errors → block (same as unavailable)

## Kill Switch scopes

`STRATEGY` | `ACCOUNT` | `GLOBAL` — persisted in D1/LocalJson registry.

`GLOBAL` engaged → all accounts blocked for new submits.

**Resume:** `HALTED` / `EMERGENCY` require operator `acknowledge` before `resume`.
CRITICAL reconciliation source must be cleared before account resume.

## API

```python
SafetyService(store, registry, *, portfolio_service, oms_service=None)

.decide(account_id, intent, *, strategy_id="", prices=None, context=None)
.is_blocked(account_id, *, strategy_id="") -> bool
.engage_kill_switch(scope, scope_id, *, reason, operator="")
.disengage_kill_switch(...)  # GLOBAL needs acknowledge
.acknowledge(event_id | "SCOPE|scope_id", *, operator)
.resume(scope, scope_id, *, operator)
.report_source(kind, scope, scope_id, *, severity, payload)
.emergency_stop(...)  # Contract only; no auto flatten
.upsert_rule(SafetyRule)
.get_state / .list_events

OMSService.set_trading_gate(safety.gate)  # prefer gate.decide (Fail-Closed)

ReconciliationService(..., safety_service=safety)  # CRITICAL → report_source
```

## Storage

- D1: [`workers/qd-research-d1/migrations/0022_safety.sql`](../../../workers/qd-research-d1/migrations/0022_safety.sql)
- R2/local event detail: `qd/production/safety/{scope}/{yyyy}/{mm}/{dd}/{event_id}.json`
- Hot path `safety_state` / `kill_switch` → registry only (not R2)

## Non-goals (P0)

```text
❌ Auto FLATTEN / corrective orders
❌ Auto-resume CRITICAL / GLOBAL / EMERGENCY
❌ Monitoring UI / LIVE funded trading
❌ Merge live_trading domain
❌ Replace Risk Engine 6C
```

## Verification

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6g_safety.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6g_safety.py -q --confcutdir=tests/research_data
```

**Next:** observability and immutable audit — [08_ops_monitoring.md](08_ops_monitoring.md) (Phase 6H).
