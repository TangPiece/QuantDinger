# Phase 4 — Factor Lab

> **Status:** Phase 4A–4F implemented. 4G+ (Neutralization / …) not started.

## Roadmap

```text
Phase 4A  Factor Definition / Registry   ← done
Phase 4B  Factor Computation             ← done
Phase 4C  Factor Evaluation              ← done
Phase 4D  IC / RankIC / ICIR             ← done
Phase 4E  Group Return / Turnover        ← done
Phase 4F  Stability / Decay              ← done
Phase 4G  Neutralization
Phase 4H  Factor Combination
Phase 4I  Factor Portfolio
```

## Reading

1. [01_factor_definition.md](01_factor_definition.md)
2. [02_factor_computation.md](02_factor_computation.md)
3. [03_factor_evaluation.md](03_factor_evaluation.md)
4. [04_factor_metrics.md](04_factor_metrics.md)
5. [05_factor_groups.md](05_factor_groups.md)
6. [06_factor_stability.md](06_factor_stability.md)

## Commands

```bash
cd backend_api_python

# 4F
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4f_factor_stability.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4f_factor_stability.py -q \
  --confcutdir=tests/research_data
```

完整 4A–4F 命令见 [COMMANDS_CN.md](../../COMMANDS_CN.md)。

## Non-goals (4A–4F)

```text
❌ Neutralization / Combination / Portfolio / UI
❌ Production Backtest / Order Execution
❌ Modify Phase 3 / l2_factors Worker
❌ Large detail rows in D1
❌ abs(IC) / guessed AUTO direction / Bull-Bear guess
❌ Weighted stability_score / decay curve fitting
```
