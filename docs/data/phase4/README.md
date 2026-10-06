# Phase 4 — Factor Lab

> **Status:** Phase 4A–4D implemented. 4E+ (Group Return / …) not started.

## Roadmap

```text
Phase 4A  Factor Definition / Registry   ← done
Phase 4B  Factor Computation             ← done
Phase 4C  Factor Evaluation              ← done
Phase 4D  IC / RankIC / ICIR             ← done
Phase 4E  Group Return / Turnover
Phase 4F  Stability / Decay
Phase 4G  Neutralization
Phase 4H  Factor Combination
Phase 4I  Factor Portfolio
```

## Reading

1. [01_factor_definition.md](01_factor_definition.md) — 4A definition / registry / hash / dataset id
2. [02_factor_computation.md](02_factor_computation.md) — 4B DAG / plan / engines / writer / PIT
3. [03_factor_evaluation.md](03_factor_evaluation.md) — 4C EvaluationSpec / ForwardReturn / SampleStatus
4. [04_factor_metrics.md](04_factor_metrics.md) — 4D IC / RankIC / ICIR

## Commands

```bash
cd backend_api_python

# 4A–4C（略，见 COMMANDS_CN）

# 4D
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4d_factor_metrics.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4d_factor_metrics.py -q \
  --confcutdir=tests/research_data
```

## Non-goals (4A–4D)

```text
❌ Group Return / Turnover / Decay / Neutralization
❌ Factor Combination / Portfolio / RD-Agent / Factor UI
❌ Modify Phase 3 Production Backtest
❌ Modify l2_factors D1 Worker behavior
❌ Qlib types in Domain
❌ Large evaluation / IC rows in D1
❌ abs(IC) by default
```
