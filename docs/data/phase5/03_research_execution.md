# Phase 5C — Cost & Execution Model

> **Status:** Implemented. Research-side execution simulation over 5A TargetPosition / 5B Backtest.
> Not Production matching. Not Level2. VWAP/TWAP are stubs only.

## Principles

```text
TargetPosition
  → OrderIntent
  → MarketRule (CN_A / HK / US)
  → ResearchExecutionSimulator (3C ExecutionSimulator facade)
  → TradeRecord + TransactionCost
  → Portfolio cash/shares
  → NAV (NET) + Attribution vs GROSS shadow
```

- **OrderIntent** is the stable interface between Strategy research and execution.
- **Do not hardcode** CN fees inside the engine loop — go through `MarketRule` / `CostPolicy`.
- **Execution price ≠ research price**: v1 forces `execution_price_adjustment=none` (raw OHLCV fills).
- **GROSS** path (default) preserves Phase 5B ideal NAV; **NET** enables costs + constraints.

## Realism modes

| Mode | Behavior |
| --- | --- |
| `GROSS` | 5B weight→shares, `NoCost`, no lot/T+1/limit |
| `NET` | OrderIntent → 3C simulator; CN_A defaults; dual-track attribution |

## CN_A defaults

Aligned with `cn_equity_close_signal_next_open`:

- Commission 3bp, stamp tax 0.1% (SELL), slippage 5bps, min commission 5 CNY
- Lot 100 floor, T+1, limit up/down, suspend skip, cash enforced

## Attribution

```text
gross_total_return
net_total_return
delta = gross - net
  ≈ commission_drag + stamp_tax_drag + slippage_drag
    + transfer_fee_drag + unfilled_drag + other
```

Persisted in `metrics/summary.json` → `attribution` and D1 `attribution_json`.

## Storage

```text
qd/backtest/{backtest_hash}/
  ...existing 5B panels...
  costs/year=/month=/part-*.parquet
  fills/year=/month=/part-*.parquet
```

D1 migration `0012_research_execution.sql` adds `realism`, `market_rule`, `execution_profile_version`, `attribution_json`.

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
        realism="NET",
        market_rule="CN_A",
    ),
    metadata={
        "cost_policy_override": {...},   # optional
        "trading_rule_override": {...},  # optional
        "trading_status_by_date": {...}, # limit/suspend injection
    },
)
```

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5c_research_execution.py
QUANTDINGER_SKIP_APP_INIT=1 python -m pytest \
  tests/research_data/test_phase5c_research_execution.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ ProductionBacktestEngine
❌ Level2 / order book / VWAP/TWAP fill model / RL
❌ Broker / OMS / live orders
❌ Qlib adapter (5D)
❌ Corporate-action full adjust on positions (v1: adjustment=none only)
❌ Hardcode CN fees inside engine loop
```
