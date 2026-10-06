# Phase 4C — Factor Evaluation Foundation

## Principle

```text
FactorDataset (4B)
  → EvaluationSpec + ReturnSpec
  → ForwardReturnEngine
  → Universe/Snapshot Alignment + SampleStatus
  → Evaluation Dataset (immutable)
  → R2 Parquet + Manifest + D1 Registry
```

4C answers **how samples are built**, not whether a factor predicts (that is 4D IC/RankIC).

## Time semantics

```text
factor_date = T
entry_date = T + execution_delay   (trading calendar)
exit_date  = T + horizon           (for close_to_close / next_open_to_close / open_to_open)
require delay>=1: factor_date < entry_date <= exit_date
```

Default research path: close signal, `execution_delay=1`, `next_open_to_close`, horizon N → T close → T+1 open entry → T+N close exit.

## Package

```text
backend_api_python/app/services/research_data/factor_lab/evaluation/
  protocol.py          # EvaluationSpec, ReturnSpec, SampleStatus, EvaluationFrame
  hash.py              # compute_evaluation_hash
  forward_return.py    # ForwardReturnEngine（唯一收益入口）
  align.py             # Universe / 停牌 / PIT / missing
  planner.py           # Spec → EvaluationPlan
  orchestrator.py      # FactorEvaluationService.run
  writers.py / artifact_store.py / repository.py
```

API（经 `factor_lab` 导出）：`FactorEvaluationService`, `EvaluationSpec`, `ReturnSpec`, `build_evaluation_plan`, `compute_evaluation_hash`, `ForwardReturnEngine`.

## ReturnSpec

| definition | entry | exit |
| --- | --- | --- |
| close_to_close | close | close |
| close_to_next_open | close | open（exit = entry + h） |
| next_open_to_close | open | close |
| open_to_open | open | open |

`horizons` 由 Spec 驱动；禁止在引擎内硬编码 1/5/10/20。

## SampleStatus

`VALID | MISSING_FACTOR | MISSING_RETURN | SUSPENDED | OUT_OF_UNIVERSE | PRICE_INVALID | PIT_INVALID`

默认保留行，统计层（4D+）再过滤。停牌不得写成 0% 收益。

## Evaluation modes

- `CROSS_SECTIONAL` — 按 `factor_date` × universe 组织（IC 基础）
- `TIME_SERIES` — 按 `instrument_key` × `factor_date` 组织

4C 只建数据契约，不计算 IC。

## Hash + Storage

`evaluation_hash` = sha256(factor_dataset_hash + normalized EvaluationSpec + return_spec + universe/snapshot + price_policy + calendar_version + evaluator_version + date_range + mode)

```text
qd/evaluation/factor/{evaluation_hash}/
  manifest.json
  year=YYYY/month=MM/part-*.parquet
```

Schema: `evaluation_panel@1`  
D1: `evaluation_dataset`（[`0003_factor_evaluation.sql`](../../../workers/qd-research-d1/migrations/0003_factor_evaluation.sql)）仅元数据。

同 hash 幂等；不同输入新 hash，禁止覆盖。

## Universe / PIT

- Snapshot **必填**；无法解析历史 membership → 硬失败，禁止回退当前成分
- PIT 沿用 Phase 1/4B：`available_time <= knowledge_time`；无效样本标 `PIT_INVALID`

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4c_factor_evaluation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4c_factor_evaluation.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ IC / RankIC / ICIR / Group Return / Turnover / Decay / Neutralization
❌ Factor Combination / Portfolio / RD-Agent / Factor UI / Online service
❌ Modify Phase 3 Production Backtest
❌ Modify l2_factors Worker
❌ Large evaluation rows in D1
```
