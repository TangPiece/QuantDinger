# Phase 4E — Group Return / Turnover / Cost-aware Evaluation

## Principle

```text
Evaluation Dataset (4C)
  → GroupSpec
  → GroupAssigner (average-rank quantiles)
  → Group Return + Long/Short
  → Turnover (0.5 Σ|Δw|; day0 = NaN)
  → CostModel (ZERO | FIXED_BPS)
  → GroupEvaluationSummary
```

This is **Factor Sorting Evaluation**, not Production Backtest (no matching / limit-up / broker).

## Package

```text
backend_api_python/app/services/research_data/factor_lab/groups/
```

API：`FactorGroupEvaluationService`, `GroupSpec`, `CostModelSpec`, `compute_group_evaluation_hash`.

## Rules

| Item | Rule |
| --- | --- |
| Groups | G1 = highest factor, GN = lowest；`group_count` ∈ {2,5,10,20} |
| Weighting | EQUAL_WEIGHT only (v1) |
| Ties | average rank；不得 `method=first` |
| Direction | POSITIVE: Long=G1 Short=GN；NEGATIVE 相反；AUTO 必须可解析否则失败 |
| Turnover | `0.5 * sum(|w_t-w_{t-1}|)`；**首日 NaN** |
| Cost | Evaluation estimate；`net = gross - estimated_cost` |
| Sample | 默认只消费 4C `VALID` |

## Storage

```text
qd/evaluation/groups/{group_evaluation_hash}/
  group_membership/...
  group_returns/...
  turnover/...
  summary.json
  manifest.json
```

D1：`factor_group_evaluation`（[`0005_factor_groups.sql`](../../../workers/qd-research-d1/migrations/0005_factor_groups.sql)）仅 Summary。

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4e_factor_groups.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4e_factor_groups.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Production Backtest / Order Execution
❌ VALUE_WEIGHT / CAGR / Sharpe / MaxDD
❌ Factor Decay / Neutralization / Combination / Portfolio / UI
❌ Recompute Forward Return / Universe / PIT
❌ Modify Phase 3 / l2_factors Worker
❌ Membership rows in D1
```
