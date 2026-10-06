# QuantDinger Backtest — Phase 3

> **Status:** Phase 3A Contract + Phase 3B Qlib Research + Phase 3C Execution Rules implemented.
> Production engine and dual-engine consistency remain later phases.

## Roadmap

```text
Phase 3A  Backtest Contract          ← done
Phase 3B  Qlib Research Backtest      ← done
Phase 3C  Cost / Slippage / Rules     ← done
Phase 3D  QuantDinger Production Backtest
Phase 3E  Dual-Engine Consistency
```

## Boundaries

| Area | Role in Phase 3 |
| --- | --- |
| `research_data/backtest/` | Domain Contract + Execution Rules (3C); **no qlib import** |
| `research_data/backtest/execution/` | OrderIntent / Cost / Eligibility / Simulator (3C) |
| `research_data/backtest_qlib/` | Qlib Research adapter (3B) |
| `research_data` Phase 2 | Experiment → Signal → TargetPosition inputs |
| `strategy_v2` / Agent backtest | Strategy API V2; **not** replaced |
| Qlib | Research engine adapter (3B+) |
| `instrument_rules.py` | Live/crypto rules snapshots; Production 3D consumes |

## Reading order

1. [01_backtest_contract.md](01_backtest_contract.md)
2. [02_execution_policy.md](02_execution_policy.md)
3. [03_price_cost_policy.md](03_price_cost_policy.md)
4. [04_trading_rules.md](04_trading_rules.md)
5. [05_result_schema.md](05_result_schema.md)
6. [06_dual_engine_consistency.md](06_dual_engine_consistency.md)
7. [07_qlib_research_backtest.md](07_qlib_research_backtest.md)
8. [08_trading_cost_execution.md](08_trading_cost_execution.md)

Index from research data phases: [../data/phase3/README.md](../data/phase3/README.md).
