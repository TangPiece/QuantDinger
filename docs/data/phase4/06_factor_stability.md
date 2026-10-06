# Phase 4F — Factor Stability / Decay

## Principle

```text
Evaluation Dataset (4C)
  → StabilitySpec
  → CrossSectionalICEngine (reuse 4D)
  → GroupAssigner + GroupReturnCalculator (reuse 4E, same-run frames)
  → Rolling IC / Distribution / Decay / Group Stability / Regime
  → FactorStabilitySummary
```

Answers: is the factor persistently predictive, how fast does signal decay, and is it stable across calendar regimes?

## Package

```text
backend_api_python/app/services/research_data/factor_lab/stability/
```

API：`FactorStabilityService`, `StabilitySpec`, `compute_stability_hash`.

## Rules

| Item | Rule |
| --- | --- |
| Rolling | Trailing window ending at T；**only** `IC <= T`（no look-ahead） |
| Windows | Configurable；default `[20,60,120,252]` |
| Decay | Observation table Horizon → IC / RankIC / L/S；**no** half-life fit |
| Group Stability | Consume same-run `GroupReturnRow`；do not re-invent formation |
| Regime v1 | `YEAR` / `QUARTER` only；no Bull/Bear guess |
| Score | Store raw metrics；**no** weighted `stability_score` |
| Sample | Default 4C `VALID` only |

## Storage

```text
qd/evaluation/stability/{stability_hash}/
  rolling_ic/year=/month=/part-*.parquet
  decay/part-*.parquet
  group_stability/year=/month=/part-*.parquet
  regime/part-*.parquet
  summary.json
  manifest.json
```

D1：`factor_stability_evaluation`（[`0006_factor_stability.sql`](../../../workers/qd-research-d1/migrations/0006_factor_stability.sql)）仅 Summary。

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4f_factor_stability.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4f_factor_stability.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Factor Neutralization / Combination / Portfolio / UI
❌ Production Backtest / Order Execution
❌ Bull/Bear/Sideways auto inference
❌ Decay curve fitting / half-life / ARIMA
❌ Weighted stability_score
❌ Recompute Evaluation Dataset / new Group Formation
❌ Modify Phase 3 / l2_factors Worker
❌ Detail rows in D1
```
