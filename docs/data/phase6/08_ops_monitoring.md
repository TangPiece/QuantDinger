# Phase 6H — Monitoring / Audit / Alert

## Goal

Three separate chains:

```text
Monitoring  → Is the system healthy now?
Audit       → What happened (immutable facts)?
Alert       → Does a human need to act?
```

Engine version: `qd_ops@1`.

Ops does **not** create orders, mutate positions, or replace Safety / Reconciliation.

```text
OMS / Safety / Reconciliation ──hooks──► OpsService
                                              │
                         Health / Audit / Alert / Incident
```

## Health

`HealthStatus`: `HEALTHY` | `DEGRADED` | `UNHEALTHY`

Aggregation: any component `UNHEALTHY` → overall `UNHEALTHY`; else any `DEGRADED` → overall `DEGRADED`; else `HEALTHY`.

## Audit

`AuditEvent` is **append-only** (no overwrite). State changes use new events (`KILL_SWITCH_ON` → `SAFETY_ACKNOWLEDGE` → `SAFETY_RESUME`).

Required actor: `actor_type` + `actor_id` (`SYSTEM` | `OPERATOR` | …).

## Trace

`OrderIntent.trace_id` → `Order.metadata['trace_id']` → audit / incident correlation.

## Metrics

Low-cardinality counters only: labels `broker`, `account`, `strategy` — **never** `symbol` as a Prometheus label.

## Alert → Safety

Only configured **CRITICAL** rules map to `SafetyService.report_source`:

- `RECON_CRITICAL` → `RECONCILIATION_CRITICAL`
- `UNEXPECTED_FILL` → `UNEXPECTED_FILL`

`WARNING` (e.g. broker latency) fires alerts but does **not** halt trading.

## API

```python
OpsService(registry, *, artifact_store, safety_service=None, broker_port=None)

.emit_audit / .list_audit_events / .get_trace(trace_id)
.collect_health(account_id)
.evaluate_alerts(signals, account_id=...)
.notify_reconciliation_critical(account_id, ...)
.notify_safety_block(...)
.audit_kill_switch / .audit_safety_acknowledge / .audit_safety_resume
.report_broker_disconnect / .report_broker_recovery
.seed_default_rules()

OMSService.set_ops_service(ops)
SafetyService(..., ops_service=ops)
ReconciliationService(..., ops_service=ops)
```

## Storage

- D1: [`workers/qd-research-d1/migrations/0023_ops_monitoring.sql`](../../../workers/qd-research-d1/migrations/0023_ops_monitoring.sql)
- R2/local audit: `qd/production/audit/{yyyy}/{mm}/{dd}/{event_id}.json`
- R2/local incidents: `qd/production/incidents/{incident_id}.json`

## Non-goals (P0)

```text
❌ Grafana / ELK / Kafka observability stack
❌ live_trading / strategy_v2 / qlib imports inside ops_service
❌ Auto Kill Switch on WARNING latency
```

## Verification

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase6h_ops.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6h_ops.py -q --confcutdir=tests/research_data
```

See also [07_safety.md](07_safety.md) for the trading gate; Ops observes Safety actions but does not own the gate.
