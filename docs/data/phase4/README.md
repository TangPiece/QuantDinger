# Phase 4 — Factor Lab

> **Status:** Phase 4A Factor Foundation implemented. 4B+ (computation / evaluation) not started.

## Roadmap

```text
Phase 4A  Factor Definition / Registry   ← done
Phase 4B  Factor Computation
Phase 4C  Factor Evaluation
Phase 4D  IC / RankIC / ICIR
Phase 4E  Group Return / Turnover
Phase 4F  Stability / Decay
Phase 4G  Neutralization
Phase 4H  Factor Combination
Phase 4I  Factor Portfolio
```

## 4A reading

1. [01_factor_definition.md](01_factor_definition.md)

## Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4a_factor_lab.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase4a_*.py -q \
  --confcutdir=tests/research_data
```

## Non-goals (4A)

```text
❌ IC / RankIC / ICIR / Group Return / Decay / Neutralization
❌ Large-scale Factor Computation (4B)
❌ Factor Lab UI / RD-Agent
❌ Modify Phase 3 Production Backtest
❌ Modify l2_factors D1 Worker behavior
❌ Qlib types in Domain
```
