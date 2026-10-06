# Phase 3D — QuantDinger Production Backtest

> **Status:** implemented. Independent of Qlib; composes Phase 3A Contract + Phase 3C `execution/`.

## Boundaries

```text
BacktestRequest (engine=production)
  → day loop (calendar)
  → DataQuery market + trading_status → MarketBar
  → TargetPosition (signal artifact, by day)
  → OrderIntent (3C rebalance)
  → ExecutionSimulator.step (3C)
  → Trade / Position / Portfolio / Equity
  → Metrics + BacktestResult + manifest/artifact
```

| Do | Don't |
| --- | --- |
| Day-event Production engine | Change Qlib / `backtest_qlib` matching |
| Cash / T+1 / lot / limit / suspend via 3C | Introduce qlib types into Domain |
| Ledger + Metrics + local artifact/Registry | Phase 3E dual-engine compare |
| Optional `PortfolioSnapshot` PnL fields | Tick / Level2 / full margin model |
| | Rewrite 3C TradingRules / CostModel |

**Principle:** TargetPosition must not mutate Position directly — only via OrderIntent → Simulator.

## Package

```text
backend_api_python/app/services/research_data/backtest_production/
  version.py          # qd_production_backtest@1
  signal_loader.py    # target_positions.parquet → by-day targets
  market_loader.py    # DataQuery interval prefetch + daily MarketBar
  portfolio_state.py  # cash / positions / realized / cost ledger
  metrics.py          # equity_curve → BacktestMetrics
  benchmark.py        # optional single-symbol benchmark
  artifact_store.py   # result.json / manifest / parquet
  engine.py           # ProductionBacktestEngine
```

Reuse (no rule duplication):

- `backtest/execution/` — `ExecutionSimulator`, `targets_to_order_intents`, calendar, presets
- `backtest/fingerprint.py` — `compute_request_fingerprint`

## Engine.run (locked)

1. `engine != "production"` → error  
2. Load experiment; validate `dataset_hash`; require `target_positions_artifact_id`  
3. Load targets by day; prefetch market window `[start, end]`  
4. Init `PortfolioState(cash=initial_capital)` + `ExecutionSimulator`  
5. For each trading day: bars → intents (pending until intended day) → `sim.step` → ledger sync → equity  
6. Metrics; optional benchmark in `metadata`  
7. `BacktestResult(engine="production", engine_version=...)` → artifact + Registry  

**Signal day vs execution day:** With `execution_delay=T+1`, intents created on T fill on T+1. Limit/suspend rejects leave Position unchanged.

**Market load:** One `market(start,end)` prefetch; slice by day in the loop. `trading_status` remains per-day. Not a full-vectorized 10y backtest — event-driven semantics stay.

## Artifact layout

```text
qd/artifacts/backtest/{result_id}/
  result.json
  manifest.json
  equity.parquet
  trades.parquet
  positions.parquet
```

`manifest.json` includes result_id, experiment_id, dataset_hash, engine, engine_version, policy summary, snapshot_id, start/end, initial_capital, artifact keys, checksum.

## Metrics

From equity curve: total_return, annualized_return (252), volatility, sharpe, max_drawdown, calmar; turnover when trades exist; sortino / win_rate / profit_factor when data allows. Benchmark excess goes to `metadata` only.

## Verify

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3d_production_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3d_*.py -q \
  --confcutdir=tests/research_data
```

Acceptance covers: no-trade equity, buy/sell ledger, limit up/down, T+1, lot floor, cash floor, suspension, determinism.

## Non-goals

```text
❌ Modify Qlib / use qlib types in Domain
❌ Phase 3E dual-engine comparison framework
❌ Tick / Level2 / full margin-short model
❌ Rewrite 3C TradingRules / CostModel
```
