# QuantDinger Backtest — Phase 3

> **Status:** Phase 3A Backtest Contract implemented.
> No Qlib or Production engine execution in 3A.

## Roadmap

```text
Phase 3A  Backtest Contract          ← current
Phase 3B  Qlib Research Backtest
Phase 3C  Cost / Slippage / Rules
Phase 3D  QuantDinger Production Backtest
Phase 3E  Dual-Engine Consistency
```

## Boundaries

| Area | Role in Phase 3 |
| --- | --- |
| `research_data/backtest/` | Domain Contract (Request / Result / Ledger) |
| `research_data` Phase 2 | Experiment → Signal → TargetPosition inputs |
| `strategy_v2` / Agent backtest | Strategy API V2; **not** replaced by 3A |
| Qlib | Research engine adapter (3B+) |
| `instrument_rules.py` | Live/crypto rules snapshots; Production 3D consumes |

## Reading order

1. [01_backtest_contract.md](01_backtest_contract.md)
2. [02_execution_policy.md](02_execution_policy.md)
3. [03_price_cost_policy.md](03_price_cost_policy.md)
4. [04_trading_rules.md](04_trading_rules.md)
5. [05_result_schema.md](05_result_schema.md)
6. [06_dual_engine_consistency.md](06_dual_engine_consistency.md)

Index from research data phases: [../data/phase3/README.md](../data/phase3/README.md).
