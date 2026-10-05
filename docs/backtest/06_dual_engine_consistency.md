# Dual-Engine Consistency (Phase 3E preview)

Phase 3A only documents the goal.

## Same contract

```text
BacktestRequest (identical)
        │
   ┌────┴────┐
   ▼         ▼
 qlib    production
   │         │
   └────┬────┘
        ▼
 compare ledgers + metrics
```

Unified contract does **not** imply identical metrics. Differences are expected when:

- Execution delay / calendar differ
- Limit up/down enforced only on production
- Cost and slippage models differ

## Phase 3E acceptance (future)

- Same `BacktestRequest` → both engines return `BacktestResult`
- Diff tool walks `TradeRecord` streams
- Report: signal match, fill price delta, rejected orders, metric gap

No implementation in Phase 3A.
