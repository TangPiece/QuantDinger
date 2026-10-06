# Phase 4G — Factor Neutralization

## Principle

```text
Raw Factor Dataset (immutable)
  → NeutralizationSpec + ExposureProvider (PIT)
  → RegressionNeutralizer (OLS residual, FULL)
  → Neutralized Factor Dataset
  → re-enter 4C → 4D / 4E / 4F
```

Neutralization is a **Factor Transformation**, not a new Evaluation Engine.

## Package

```text
backend_api_python/app/services/research_data/factor_lab/neutralization/
```

API：`FactorNeutralizationService`, `NeutralizationSpec`, `compute_neutralization_hash`.

## Rules

| Item | Rule |
| --- | --- |
| Method v1 | `REGRESSION` OLS only；`strength=FULL` |
| Targets | `SIZE` + `INDUSTRY`；`BETA` 预留（无注入则硬失败） |
| SIZE | PIT `MARKET_CAP`（或注入）；默认 `log(market_cap)` |
| Industry | Exposure panel / 注入；one-hot drop_first |
| PIT | `available_time <= knowledge_time`（交易日收盘 KT） |
| Raw | 永不覆盖；审计保留 `raw_factor` + `neutralized_factor` |
| Diagnostics | Pearson/Spearman before/after + R² |

## Dual write (4C compatibility)

4C 只按 `FactorDatasetRecord.factor_ref` 读：

```text
qd/factor/daily/factor_set={neut_factor_ref}/...
```

同时写审计路径：

```text
qd/factor/neutralized/{neutralization_hash}/
  factor/  exposure/  diagnostics/
  summary.json  manifest.json
```

## D1

`factor_neutralization`（[`0007_factor_neutralization.sql`](../../../workers/qd-research-d1/migrations/0007_factor_neutralization.sql)）仅 Summary。

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4g_factor_neutralization.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4g_factor_neutralization.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Portfolio / UI（Combination 见 4H）
❌ Production Backtest / Order Execution
❌ Compute Beta from market bars
❌ New Level2 / market_cap ingest pipeline
❌ ML Neutralization / PARTIAL strength
❌ Overwrite Raw Factor Dataset
❌ Modify 4C–4F Evaluation engines
❌ Detail rows in D1
```
