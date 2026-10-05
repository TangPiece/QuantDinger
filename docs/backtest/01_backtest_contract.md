# Backtest Contract Overview

## Principle

QuantDinger Domain owns the contract. Engines adapt:

```text
BacktestRequest
      │
      ├── QlibAdapter (3B)
      └── ProductionAdapter (3D)
      │
      ▼
BacktestResult
```

Do **not** expose `qlib.backtest` return types as the product API.

## BacktestRequest

Core fields:

| Field | Purpose |
| --- | --- |
| `experiment_id` | Trace to Phase 2F Experiment |
| `dataset_hash` | Data fingerprint |
| `strategy_version` | Signal strategy ref |
| `engine` | `qlib` or `production` |
| `execution_policy` | Signal vs execution timing |
| `market_price_policy` | Prices for fills (backtest layer) |
| `cost_policy` | Fees / slippage (defined in 3A) |
| `trading_rule` | Lot size, T+N, limits |
| `signal_run_id` / `target_positions_artifact_id` | Optional artifact refs |

Code: `app/services/research_data/backtest/request.py`.

## BacktestResult

| Field | Purpose |
| --- | --- |
| `result_id` | Output identity |
| `request_fingerprint` | Links to request semantics |
| `equity_curve` | Portfolio equity over time |
| `trades` | Trade ledger |
| `position_history` / `portfolio_history` | Audit trail |
| `metrics` | Unified metric names |

## Engine protocol

```python
class BacktestEngine(Protocol):
    def run(self, request: BacktestRequest) -> BacktestResult: ...
```

No implementation in Phase 3A.

## Non-goals (3A)

```text
❌ Running backtests
❌ Metric calculation
❌ Changing Strategy V2 or Agent backtest APIs
```
