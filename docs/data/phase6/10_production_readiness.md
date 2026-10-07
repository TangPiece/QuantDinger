# Phase 6J — Production Readiness

## Goal

Harden 6A–6I into **engineering reliability** before 7A Live. No new trading features; no real money.

Engine version: `qd_readiness@1`.

Output:

```text
PRODUCTION_READY = TRUE | FALSE
```

## P0

| ID | Summary |
|----|---------|
| RDY-001 | Crash after SUBMITTED → `recover_on_start` (no re-submit) |
| RDY-002 | Idempotent triple submit |
| RDY-003 | Duplicate execution dedup after reconnect |
| RDY-004 | UNKNOWN → recover |
| RDY-005 | Out-of-order events → final qty correct |
| RDY-006 | Broker disconnect + reconnect merge |
| RDY-007 | LocalJson registry restart persistence |
| RDY-008 | Kill Switch strategy/account isolation |
| RDY-009 | Operator ack → resume + audit |
| RDY-010 | E2E replay + PIT leakage stub |

## API

```python
ReadinessService(...).recover_on_start()
ReadinessService(...).run_check(check_id)
ReadinessService(...).run_checklist()  # production_ready
ReadinessService(...).run_fault(fault_id)
ReadinessService(...).list_slos()
```

OMS: `OMSService.recover_on_start()` → `RecoverReport` (`resubmit_attempted` always `False`).

## Storage

- D1: `workers/qd-research-d1/migrations/0025_production_readiness.sql`
- R2/local: `qd/production/readiness/{run_id}.json`

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6j_readiness.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6j_readiness.py -q \
  --confcutdir=tests/research_data
```

Soak entry (non-gate): `scripts/soak_paper_stub.py`

## Non-goals

```text
❌ Live / Real Money / auto-enable Live
❌ New brokers / strategies / Qlib features
❌ 24h soak as merge gate
```

See: [docs/production/](../production/) runbook suite.
