# Phase 6A — Production Runtime / Online Data

## Goal

Load a **DEPLOYED** ProductionBundle (5F), drive a `TradingSession`, pull market data via Canonical/`DataQuery`, compute online features with the same evaluator as 5F Feature Parity, call `ProductionBridgeService.infer`, and emit research `OrderIntent`s under **PAPER** or **SHADOW**.

Engine version: `qd_production_runtime@1`.

## Pipeline

```text
DEPLOYED ProductionBundle (5F)
  → ProductionRuntime.load + integrity
  → TradingSession (PRE_MARKET … POST_MARKET)
  → MarketDataProvider (Historical=DataQuery / Paper realtime=as-of Canonical)
  → Online Feature (+ 5F FeatureParity 同源 evaluator)
  → ProductionBridgeService.infer  [reuse, 不重写]
  → RiskGate port (薄封装 5F SignalGate；完整 Risk 留给 6C)
  → OrderIntent (research contract)
  → STOP（不写 pending_orders / 不触 live_trading / 不触 Broker）
```

## Orchestrator API

```python
ProductionRuntimeService(store, registry, *, bridge=None, market_data=None).start(
    bundle_hash, *, market="CN_A", environment="PAPER"
) -> RuntimeInstance

.tick(runtime_id, *, now=None, metadata=None) -> RuntimeTickResult
  # OrderIntent list + run_id + events；不发单

.pause / resume / stop(runtime_id)
```

`metadata` for tests: `price_bars`, `factor_rows`, `force_new_run`, `session_phase`, `trading_date`.

## Principles

1. Stop at **OrderIntent**; `environment ∈ {PAPER, SHADOW}` only.
2. Reuse 5F `infer` + integrity/gates; do not copy freeze / second signal stack.
3. Market SSOT: research/paper path only via `DataQuery` → Canonical (no exchange REST in PAPER).
4. Session clocks live in `MarketSchedule` / `TradingCalendar` wrappers — never hardcoded into strategy rules.
5. Idempotency: same `idempotency_key` returns existing run.
6. Domain must not import `qlib`, Broker, `PendingOrderWorker`, or weaken Agent live gates.

## Domain

- `RuntimeInstance` — status machine STARTING→READY→RUNNING→PAUSED|DEGRADED→STOPPING→STOPPED|ERROR
- `TradingSession` + `SessionPhase`
- `idempotency_key` = sha256(bundle_hash + trading_date + session_phase + decision_bucket + instruments + signal_version)
- Events: `BUNDLE_LOADED`, `DATA_READY`, `FEATURE_COMPUTED`, `MODEL_INFERRED`, `SIGNAL_GENERATED`, `RISK_PASSED` / `RISK_REJECTED`, `ORDER_INTENT_CREATED`, `SESSION_PHASE`, `DATA_STALE`, `RUNTIME_PAUSED`, `RUNTIME_ERROR`

## Storage

- D1 migration: `workers/qd-research-d1/migrations/0016_production_runtime.sql`
  - `production_runtime` / `production_runtime_event` / `production_runtime_run` (UNIQUE `idempotency_key`)
- R2/local: `qd/production/runtime/{runtime_id}/` — `manifest.json`, `events/`, `runs/{run_id}/inference.json`

## Non-goals

```text
❌ LIVE broker orders / pending_orders enqueue
❌ OMS / Account / Position SSOT (6B+)
❌ Full Risk Engine (6C)
❌ Merge Strategy V2 LiveSession / Agent quick_trade
❌ Direct Qlib cache or realtime HTTP in PAPER path
❌ Hardcode 09:30/15:00 inside strategy rules
```

## Compatibility

- 5F API unchanged; only calls `infer` / registry get DEPLOYED
- Research `OrderIntent` unchanged; idempotency lives in `runtime_run`
- Tick result metadata carries `runtime_id` + `run_id` for Phase 6B Portfolio consumption
