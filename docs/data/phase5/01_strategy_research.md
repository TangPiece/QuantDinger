# Phase 5A — Strategy Research Foundation

## Principle

```text
FactorDataset
  → SignalDefinition → Signal (PIT times)
4I portfolio_hash
  → TargetPosition
  → StrategySpec (Rebalance + Holding)
  → strategy_hash
  → R2 qd/strategy/{hash}/ + D1 Registry
```

This is **Strategy Contract materialization**, not Backtest.

## Package

```text
backend_api_python/app/services/research_data/strategy_research/
```

API：`StrategyResearchService.materialize`, `StrategySpec`, `compute_strategy_hash`.

## Rules

| Item | Rule |
| --- | --- |
| Signal source | FactorDataset only（Qlib Prediction → 5D） |
| PIT | `resolve_signal_times`：T 收盘 knowledge → T+1 开盘 execution |
| Look-ahead | `execution_time > knowledge_time` 硬失败 |
| Portfolio | 只读引用 `portfolio_hash`；factor_dataset_id / rebalance_frequency 必须一致 |
| Holding | `HOLD_UNTIL_NEXT_REBALANCE` only |
| Returns | **不计算** |

## Storage

```text
qd/strategy/{strategy_hash}/
  signals/
  target_positions/
  snapshots/strategy_spec.json
  summary.json  manifest.json
```

D1：`research_strategy` + `research_strategy_version`（[`0010_strategy_research.sql`](../../../workers/qd-research-d1/migrations/0010_strategy_research.sql)）。

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5a_strategy_research.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5a_strategy_research.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Research / Qlib / Production Backtest
❌ Fees / Slippage / Limit-up / OMS / TWAP / Broker
❌ stop_loss / take_profit / time_stop
❌ Modify 4A–4I / signal Prediction pipeline / Strategy API V2
❌ Recompute 4I portfolio or Forward Return
❌ Detail rows in D1
❌ Strategy NAV / Sharpe in 5A
```
