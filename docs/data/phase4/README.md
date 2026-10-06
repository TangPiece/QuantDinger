# Phase 4 — Factor Lab

> **Status:** Phase 4A–4I implemented. Factor Lab research loop complete；下一步见 [Phase 5A](../phase5/01_strategy_research.md)。

## Roadmap

```text
Phase 4A  Factor Definition / Registry   ← done
Phase 4B  Factor Computation             ← done
Phase 4C  Factor Evaluation              ← done
Phase 4D  IC / RankIC / ICIR             ← done
Phase 4E  Group Return / Turnover        ← done
Phase 4F  Stability / Decay              ← done
Phase 4G  Neutralization                 ← done
Phase 4H  Factor Combination             ← done
Phase 4I  Factor Portfolio               ← done
```

## Reading

1. [01_factor_definition.md](01_factor_definition.md)
2. [02_factor_computation.md](02_factor_computation.md)
3. [03_factor_evaluation.md](03_factor_evaluation.md)
4. [04_factor_metrics.md](04_factor_metrics.md)
5. [05_factor_groups.md](05_factor_groups.md)
6. [06_factor_stability.md](06_factor_stability.md)
7. [07_factor_neutralization.md](07_factor_neutralization.md)
8. [08_factor_combination.md](08_factor_combination.md)
9. [09_factor_portfolio.md](09_factor_portfolio.md)

## Commands

```bash
cd backend_api_python

# 4I
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4i_factor_portfolio.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4i_factor_portfolio.py -q \
  --confcutdir=tests/research_data
```

完整 4A–4I 命令见 [COMMANDS_CN.md](../../COMMANDS_CN.md)。

## Non-goals (4A–4I)

```text
❌ Mean-Variance / Risk Parity / UI / ML Combination
❌ Production Backtest / Order Execution
❌ Modify Phase 3 / l2_factors Worker
❌ Large detail rows in D1
❌ abs(IC) / guessed AUTO direction / Bull-Bear guess
❌ Weighted stability_score / decay curve fitting
❌ Compute Beta / new market_cap ingest / overwrite Raw Factor
❌ Recompute IC inside Combination / auto full 4D–4G re-eval
❌ Fees / Slippage / Limit-up inside Factor Portfolio
```
