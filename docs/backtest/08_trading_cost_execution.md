# 08 — Trading Cost & Execution Rules (Phase 3C)

> **Status:** Implemented.
> Engine-agnostic execution semantics for QuantDinger.
> Does **not** modify Qlib; does **not** implement Production Backtest (3D).

## Pipeline

```text
TargetPosition + PortfolioSnapshot
  → OrderIntent (rebalance delta)
  → ExecutionPolicy / TradingRule / CostPolicy
  → ExecutionDecision
  → ExecutionSimulator (daily)
  → TradeRecord + Position / Portfolio
```

Package: [`backend_api_python/app/services/research_data/backtest/execution/`](../../backend_api_python/app/services/research_data/backtest/execution/)  
(Domain contract remains in `backtest/`; **no** `import qlib`.)

## Two modes (keep separate)

| Mode | Path |
| --- | --- |
| Research (3B) | TargetPosition → Qlib Strategy / Exchange → BacktestResult |
| Execution-aware (3C) | TargetPosition → OrderIntent → Rules / Cost → Trade |

## Contract locks

### Lot rounding (`TradingRule.lot_rounding`)

| Value | Behavior |
| --- | --- |
| `floor` (CN default) | Qty floored to `lot_size`; remainder → `rejected_quantity`, reason `LOT_SIZE_FLOOR` |
| `reject` | Non-multiple → whole order rejected, reason `LOT_SIZE_REJECT` |

Example: `155` with `lot_size=100` → executable `100`, rejected `55`.

### T+1

- `ExecutionPolicy.execution_delay=T+1` → `intended_execution_time` on next session day.
- Simulator on signal day: `EXECUTION_DELAY` (no fill).
- `TradingRule.t_plus>=1`: shares bought today are not sellable same day (`T_PLUS`).

### Limits / suspension

| Case | Decision |
| --- | --- |
| Limit up + BUY | `executable=false`, `LIMIT_UP` |
| Limit down + SELL | `executable=false`, `LIMIT_DOWN` |
| Suspended | BUY/SELL rejected (`SUSPENDED`); `fail` raises; `hold` → `HOLD` |

### Cost

```text
CostBreakdown: commission, stamp_tax, transfer_fee, slippage, other_fee, total_cost
BUY:  net_cash_delta = -(gross + total_cost)
SELL: net_cash_delta = +(gross - total_cost)
```

CN: stamp tax on SELL → `TradeRecord.tax`; commission+transfer → `TradeRecord.commission`.

### Markets via rules (not hardcoded)

Presets: `cn_equity_close_signal_next_open` / `cn_a_share_execution_bundle`, `us_equity_t0_close`, `hk_equity_t0_close`.  
Simulator reads `TradingRule` fields only.

## Non-goals

```text
❌ Production Backtest Engine
❌ Modify Qlib / backtest_qlib
❌ Tick / Level2 / order book / VWAP / TWAP / RL
❌ strategy_v2 / Agent backtest
❌ Dual-engine consistency (3E)
```

## Verify

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3c_execution_rules.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3c_*.py -q \
  --confcutdir=tests/research_data
```
