# Phase 9D — Factor Mining

## 目标

在 9B FeatureSet + 9C Evaluation 之上，用**可复现**策略（`random_seed` + `MiningPolicy`）在 **factor_lab DSL 模板**空间内搜索 FactorCandidate，经 Fast Screen → Dedup → Full Eval → Holdout 报告，**不**自动写入生产 Factor Registry / Promotion。

```text
FeatureUniverse (pinned columns / FeatureSet)
  → Exhaustive | Random (seed 必填)
  → Expression AST → canonical DSL
  → Fast Screen
  → Expression (+ optional 4H corr) Dedup
  → 9B register/build + 9C run_evaluation (survivors)
  → Holdout 指标（不参与 ranking）
  → MiningRunIndex + FactorCandidate[]
  ✕ GP 默认引擎 / 完整 FDR / auto APPROVED / Strategy promotion
```

## 包位置

`backend_api_python/app/services/research_data/mining_platform/`

| 模块 | 职责 |
| --- | --- |
| `expression/` | 薄 AST；`lower_to_dsl` 仅输出 `momentum_N` / `volatility_N` / `rolling_*` / `Ref` / ratio |
| `generators/` | `exhaustive_small` / `random_search` |
| `screen.py` | Fast Screen（proxy IC / inject） |
| `dedup.py` | `expression_hash` + 可选相关冗余 |
| `orchestrator.py` | 编排 9B + 9C + holdout + ranking |
| `runner.py` | `FactorMiningService` 门面 |

`ENGINE_VERSION=qd_mining_platform@1`

## Service API

```python
FactorMiningService(store, registry, *,
    factor_svc=None, eval_svc=None, dataset_svc=None)

.run_mining(job: MiningJob | dict, *, inject=None) -> MiningRun
.get_run(mining_run_id) / .list_candidates(mining_run_id)
.promote_candidate_to_draft(candidate_id)  # 显式 DRAFT，非 APPROVED
```

**无** `auto_approve` / `promote_strategy` / `genetic_default` / `capacity_curve`。

## 复现键

```text
mining_run_hash = SHA256(
  dataset_hash | feature_set_hash | mining_policy_content_hash
  | evaluation_policy_version | random_seed | engine_version
)
```

同 seed + 同 policy → 相同 `expression_hash` 集合；Completed run 幂等返回。

## Multiple testing

记录 `total_candidates_tested` 与 `selection_bias_warning`；完整 Bonferroni/FDR 延后。

## Non-goals（9D）

```text
❌ Genetic Programming 作为默认核心
❌ 完整 Bonferroni / FDR / Deflated Sharpe
❌ Capacity curve
❌ Candidate 自动 APPROVED / Strategy promotion
❌ 任意嵌套非 DSL 表达式树
❌ 新 D1 表（LocalJson + R2 index）
```

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9d_factor_mining.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9d_factor_mining.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9c_factor_evaluation.py` 绿。
