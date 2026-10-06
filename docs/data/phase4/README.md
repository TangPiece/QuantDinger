# Phase 4 — Factor Lab

> **Status:** Phase 4A Factor Foundation + Phase 4B Factor Computation implemented. 4C+ (evaluation) not started.

## Roadmap

```text
Phase 4A  Factor Definition / Registry   ← done
Phase 4B  Factor Computation             ← done
Phase 4C  Factor Evaluation
Phase 4D  IC / RankIC / ICIR
Phase 4E  Group Return / Turnover
Phase 4F  Stability / Decay
Phase 4G  Neutralization
Phase 4H  Factor Combination
Phase 4I  Factor Portfolio
```

## Reading

1. [01_factor_definition.md](01_factor_definition.md) — 4A definition / registry / hash / dataset id
2. [02_factor_computation.md](02_factor_computation.md) — 4B DAG / plan / engines / writer / PIT

## Commands

```bash
cd backend_api_python

# 4A
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4a_factor_lab.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase4a_*.py -q \
  --confcutdir=tests/research_data

# 4B
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4b_factor_compute.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4b_factor_compute.py -q \
  --confcutdir=tests/research_data
```

## Non-goals (4A + 4B)

```text
❌ IC / RankIC / ICIR / Group Return / Decay / Neutralization
❌ Factor Lab UI / RD-Agent / online factor service
❌ Full Alpha158 generator
❌ Modify Phase 3 Production Backtest
❌ Modify l2_factors D1 Worker behavior
❌ Qlib types in Domain
```
