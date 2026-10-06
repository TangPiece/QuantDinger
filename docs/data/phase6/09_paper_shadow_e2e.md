# Phase 6I — Paper / Shadow E2E

## Goal

Prove **6A–6H compose into one machine** without new trading features or real money.

Engine version: `qd_e2e@1`.

```text
TargetPosition (injected)
        ↓
6B apply_targets (SHADOW_DRY)
        ↓
6C Risk → OrderIntent
        ↓
6G Safety Gate
        ↓
6D OMS → 6E Simulated/Paper Broker
        ↓
6B Position ← Fill
        ↓
6F Reconciliation
        ↓
6H Audit / Health
```

**SHADOW** stops after OrderIntent and records `virtual_order` (no broker submit).

## Modes

| Mode | Behavior |
|------|----------|
| `PAPER` | Full chain via `SANDBOX` + SimulatedBroker |
| `SHADOW` | Intent only + VirtualOrder |
| `PAPER_REAL_MD` | Same as PAPER; optional real-shaped bars in metadata |

Forbidden: `LIVE`, funded accounts, `live_trading` imports in `e2e_service`.

## Scenarios (P0)

| ID | Summary |
|----|---------|
| E2E-001 | Partial → fill → position → recon |
| E2E-002 | Reject |
| E2E-003 | Limit cancel |
| E2E-004 | Partial → cancel |
| E2E-005 | Broker disconnect → health DEGRADED |
| E2E-006 | Duplicate execution dedup |
| E2E-007 | UNKNOWN → recover |
| E2E-008 | Position mismatch → Safety BLOCK |
| E2E-009 | Risk REJECT |
| E2E-010 | Kill switch → block + audit |

Default path: **inject TargetPosition** (no Qlib import in default scenarios).

## Identity

`dataset_hash`, `strategy_version`, `trace_id` stamped on intents and propagated to `Order.metadata` via OMS submit metadata.

## API

```python
E2EService(store, registry, portfolio_service=..., risk_service=..., oms_service=...,
           safety_service=..., recon_service=..., ops_service=...)

.start_session / .close_session / .get_session
.run_scenario(scenario_id, mode="PAPER")
.run_suite(mode="PAPER")
.replay(ReplayRequest)
.consistency_score(run_id)
.shadow_compare(paper_run_id, shadow_run_id)
```

## Storage

- D1: [`workers/qd-research-d1/migrations/0024_e2e.sql`](../../../workers/qd-research-d1/migrations/0024_e2e.sql)
- R2/local: `qd/production/e2e/{session_id}/{run_id}.json`

## Non-goals (P0)

```text
❌ Live / Real Money
❌ New trading features / new brokers
❌ Vue E2E Dashboard
❌ Replace Risk / Safety / Recon implementations
❌ Mandatory Qlib train in default E2E suite
```

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6i_e2e.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6i_e2e.py -q \
  --confcutdir=tests/research_data
```

See also: [08_ops_monitoring.md](08_ops_monitoring.md) (Ops hooks used by E2E audit).
