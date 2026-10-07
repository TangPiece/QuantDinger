# Phase 9C — Factor Evaluation Engine

## 目标

在 9B `FactorBuildIndex` 之上，用统一 `EvaluationPolicy` 编排既有 4C–4F（IC / 分位 / 稳定性），发布不可变 `EvaluationRunIndex` 与薄层 `FactorQualityScore`。**不重写** IC/分层数学，**不**直连 Phase 8 Promotion。

```text
9B FactorBuildIndex (factor_hash + dataset_hash)
  → EvaluationQualityGate (PIT / lineage / build 钉住)
  → EvaluationPolicy → EvaluationSpec (4C)
  → 4D IC → 4E Quantile+Cost → 4F Stability
  → EvaluationRunIndex + QualityScore (raw 指标保留)
  ✕ Capacity curve / Mining / Promotion
```

## 包位置

`backend_api_python/app/services/research_data/evaluation_platform/`

| 模块 | 职责 |
| --- | --- |
| `policy.py` / `policy_presets.py` | `EvaluationPolicy`，preset `default_equity_factor_v1` |
| `quality_gate.py` | 9A handle + 9B build 校验；失败 → `BLOCKED` |
| `adapters.py` | Policy → 4C/4D/4E/4F Spec |
| `orchestrator.py` | 4C→4D→4E→4F 顺序编排 |
| `score.py` | 薄层 QualityScore（非唯一真相） |
| `runner.py` | `FactorEvaluationPlatformService` 门面 |

`ENGINE_VERSION=qd_evaluation_platform@1`

## Service API

```python
FactorEvaluationPlatformService(store, registry, *,
    factor_svc=None, dataset_svc=None, query=None, canonical_store=None)

.run_evaluation(factor_ref, dataset_ref, *,
    policy_id="default_equity_factor_v1", window=(start, end), inject=None)
.get_run(evaluation_id) / .get_by_hash(run_content_hash)
.list_runs(factor_hash=None)
.get_quality_score(evaluation_id)
.get_lineage(evaluation_id)
```

**无** `mine` / `promote` / `capacity_curve` / `train_model`。

## 幂等与不可变

- `run_content_hash = SHA256(factor_hash, dataset_hash, factor_dataset_id, policy_content_hash, window, layout, ENGINE_VERSION)`
- 同 hash 槽位：`EvaluationRunIndex` 不可覆盖；同输入重复调用返回已有 run
- 修改 `EvaluationPolicy` 内容 → 新 `policy_content_hash` → 新 run

## Gate

- `PASS`：进入 4C–4F，写入 IC/分层/stability 指针
- `BLOCKED`：写 run 索引（`status=BLOCKED`），**不**写 IC/分层/stability 产物

## Non-goals（9C）

```text
❌ Capacity analysis platform
❌ Multi-factor correlation facade (4H 仍用原入口)
❌ Factor mining (9D)
❌ Direct Promotion from Evaluation
❌ 重写 4C–4F 引擎
❌ 默认 D1 新表（run/score → LocalJson + artifact 镜像）
```

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9c_factor_evaluation.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9c_factor_evaluation.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9b_feature_factor_platform.py` 绿。
