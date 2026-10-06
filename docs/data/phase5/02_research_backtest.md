# Phase 5B — Research Backtest Engine

> **Status:** Implemented. Research NAV / metrics / benchmark over 5A Strategy Contract.
> Not a production matching engine. Not Qlib. Cost models deferred to 5C.

## Principles

```text
5A strategy_hash
  → TargetPosition Dataset
  → BacktestSpec (window, execution_policy, benchmark)
  → ResearchBacktestEngine (weight → shares, mark-to-market, NoCost)
  → Daily NAV / Returns / Positions / Turnover
  → PerformanceMetrics (+ optional Benchmark)
  → R2 qd/backtest/{backtest_hash}/ + D1 Summary
```

- **Do not recompute Factor.** Consume 5A TargetPosition only.
- **Do not modify Strategy.** Same `strategy_hash` can be backtested on multiple windows.
- **Reproducible:** `backtest_hash` pins strategy + window + policy + engine versions.
- **No Production / Qlib engines.** Own controlled research baseline for 5E cross-validation.

## Time model

Default **`NEXT_OPEN`**:

```text
T close → Signal / TargetPosition available
T+1 open → theoretical fill
T+1 close → mark-to-market
```

Also supported:

| Mode | Execution date | Fill field | Note |
| --- | --- | --- | --- |
| `NEXT_OPEN` | next trading day | `open` | **default** |
| `NEXT_CLOSE` | next trading day | `close` | |
| `SAME_CLOSE` | signal date | `close` | explicit look-ahead; `allows_same_close=true` |

## Cost

`ExecutionCostModel` Protocol + `NoCostModel` (commission = slippage = tax = 0).
Real costs → Phase 5C.

## Storage

```text
qd/backtest/{backtest_hash}/
  portfolio/year=/month=/part-*.parquet
  returns/year=/month=/part-*.parquet
  positions/year=/month=/part-*.parquet
  turnover/year=/month=/part-*.parquet
  metrics/summary.json
  summary.json
  manifest.json
```

D1 table `research_backtest_run` (migration `0011`) stores Summary only — no daily NAV/positions.

## API

```python
from app.services.research_data.research_backtest import (
    BacktestSpec,
    ResearchBacktestService,
    ResearchExecutionPolicy,
)

result = ResearchBacktestService(store, registry).run(
    strategy_hash,
    BacktestSpec(
        strategy_hash=strategy_hash,
        start_date=...,
        end_date=...,
        execution_policy=ResearchExecutionPolicy(mode="NEXT_OPEN"),
    ),
    metadata={
        # tests may inject:
        # "targets_by_date", "price_bars", "benchmark_returns", "force_recompute"
    },
)
```

## Metrics (252)

Total Return, Ann. Return, Ann. Vol, Sharpe (rf=0), Max Drawdown, Calmar, Win Rate, mean Turnover.
Daily return series are persisted — not summary-only.

## Benchmark

`NONE` | `INDEX` (Canonical price panel) | `CUSTOM` (injected `benchmark_returns`).

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5b_research_backtest.py
QUANTDINGER_SKIP_APP_INIT=1 python -m pytest \
  tests/research_data/test_phase5b_research_backtest.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ ProductionBacktestEngine / ExecutionSimulator / Qlib Backtest
❌ Commission / Stamp / Slippage / Limit-up / T+1 / Lot size / Volume
❌ TWAP/VWAP / Level2 / Broker / OMS
❌ Recompute Factor / Modify 5A Strategy
❌ Corporate action adjustment (v1 IGNORE)
❌ Detail rows in D1
```
