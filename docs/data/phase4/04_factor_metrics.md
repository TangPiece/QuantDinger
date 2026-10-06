# Phase 4D — IC / RankIC / ICIR

## Principle

```text
Evaluation Dataset (4C)
  → MetricSpec
  → Daily Cross-Section Pearson IC / Spearman RankIC
  → MetricTimeSeries
  → ICStatisticsAggregator
  → FactorEvaluationSummary
  → R2 Artifact + D1 Summary
```

4D **only statistics**. No Forward Return / Universe / PIT / Factor Computation.

## Definitions

| Metric | Definition |
| --- | --- |
| IC | Pearson corr(factor, forward_return) per `factor_date` × horizon |
| RankIC | Spearman corr (rank then Pearson) |
| ICIR | `mean(IC) / sample_std(IC)` with **ddof=1** |
| t-stat | `mean / (std / sqrt(N))`, N = valid_day_count |

- Never `abs(IC)` / `abs(RankIC)`.
- Constant factor/return or `n < min_cross_section_size` → NaN + `valid=False`.
- Default consume only `sample_status=VALID` from 4C.

## Package

```text
backend_api_python/app/services/research_data/factor_lab/metrics/
  protocol.py / hash.py / calculators.py / aggregator.py
  orchestrator.py / writers.py / artifact_store.py / repository.py
```

API：`FactorMetricsService`, `MetricSpec`, `compute_metric_hash`, `FactorEvaluationSummary`.

## MetricSpec

- `evaluation_hash`, `horizons` (or infer `forward_return_{N}d`)
- `min_cross_section_size` (default 30)
- `allowed_sample_status` (default `["VALID"]`)
- `direction`: `AUTO` | `POSITIVE` | `NEGATIVE` (label only; no abs)
- `metric_version` / `calculator_version`

## Storage

```text
qd/evaluation/metrics/{metric_hash}/
  ic/year=YYYY/month=MM/part-*.parquet
  summary.json
  manifest.json
```

Schema: `metric_ic_daily@1`  
D1: `factor_evaluation_summary` ([`0004_factor_metrics.sql`](../../../workers/qd-research-d1/migrations/0004_factor_metrics.sql)) — summary only, PK `(metric_hash, horizon)`.

`metric_hash` = sha256(evaluation_hash + normalized MetricSpec + versions).

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4d_factor_metrics.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4d_factor_metrics.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Group Return / Turnover / Decay / Neutralization
❌ Factor Combination / Portfolio / UI / RD-Agent
❌ Recompute Forward Return / Universe / PIT
❌ Modify Phase 3 Backtest / l2_factors Worker
❌ Daily IC rows in D1
❌ abs(IC) by default
```
