# Phase 4H — Factor Combination

## Principle

```text
FactorDataset_1..N  (建议已 4G 中性化，但不强制)
  → CombinationSpec
  → Align (inner join on date×instrument)
  → CS Normalize (RANK | ZSCORE)
  → Correlation + Redundancy
  → Weighting (EQUAL | IC | CORR_ADJUSTED) 或 Orthogonalize→EQUAL
  → Composite Factor Dataset
  → R2 qd/factor/combined/{combination_hash}/ + D1 Summary
  → 可再进 4C → 4D/4E/4F/4G
```

Combination is a **Factor Transformation**, not Portfolio Optimization / Evaluation Engine.

## Package

```text
backend_api_python/app/services/research_data/factor_lab/combination/
```

API：`FactorCombinationService`, `CombinationSpec`, `compute_combination_hash`.

## Rules

| Item | Rule |
| --- | --- |
| Input | `factor_dataset_id` 列表（≥2）；不吃 `evaluation_hash` |
| Align | `trading_date × instrument_key` inner join；`DROP_ROW` |
| Normalize | 截面 `RANK`（default）或 `ZSCORE` |
| Correlation | 日截面相关 → 跨日均值；`|corr|≥threshold` 记冗余（不自动剔除） |
| Weights | `EQUAL` / `IC_WEIGHT` / `CORR_ADJUSTED`；IC 来自 `member_ic`（不重算 IC） |
| Ortho | Gram-Schmidt 后 EQUAL；权重记等权 + `orthogonalized=true` |
| Source | 成员 Dataset 不可变；新 `factor_ref` 如 `composite@c_{hash12}` |

## Dual write (4C compatibility)

```text
qd/factor/combined/{combination_hash}/
  composite/  correlation/  weights/
  summary.json  manifest.json

qd/factor/daily/factor_set={composite_factor_ref}/   # 4C 读路径
qd/dataset/factor/{composite_factor_dataset_id}/manifest.json
```

## D1

`factor_combination`（[`0008_factor_combination.sql`](../../../workers/qd-research-d1/migrations/0008_factor_combination.sql)）仅 Summary。

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4h_factor_combination.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4h_factor_combination.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ ML Combination / Auto mining / RD-Agent
❌ Portfolio Optimization / Risk budgeting
❌ Recompute IC inside Combination (use member_ic)
❌ Auto full 4D–4G re-eval pipeline
❌ Overwrite member Factor Datasets
❌ Modify 4C–4G engines / Level2
❌ Detail rows in D1
```
