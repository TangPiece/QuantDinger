# Phase 3 — Research Backtest

> **Status:** Phase 3A–3D implemented. Phase 3E dual-engine consistency is next.

## Reading order

### 3A — Contract (done)

See [../../backtest/README.md](../../backtest/README.md):

1. [01_backtest_contract.md](../../backtest/01_backtest_contract.md)
2. [02_execution_policy.md](../../backtest/02_execution_policy.md)
3. [03_price_cost_policy.md](../../backtest/03_price_cost_policy.md)
4. [04_trading_rules.md](../../backtest/04_trading_rules.md)
5. [05_result_schema.md](../../backtest/05_result_schema.md)
6. [06_dual_engine_consistency.md](../../backtest/06_dual_engine_consistency.md)

### 3B — Qlib Research Backtest (done)

7. [07_qlib_research_backtest.md](../../backtest/07_qlib_research_backtest.md)

### 3C — Trading Cost & Execution Rules (done)

8. [08_trading_cost_execution.md](../../backtest/08_trading_cost_execution.md)

### 3D — Production Backtest (done)

9. [09_production_backtest.md](../../backtest/09_production_backtest.md)

### 3E (planned)

| Phase | Topic |
| --- | --- |
| 3E | Dual-engine consistency analysis |

## Prerequisite

Phase 2F Experiment & Reproducibility must PASS ([../phase2/06_experiment_reproducibility.md](../phase2/06_experiment_reproducibility.md)).

## Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase3a_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase3b_qlib_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3c_execution_rules.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3d_production_backtest.py
```
