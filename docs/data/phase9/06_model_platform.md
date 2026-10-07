# Phase 9F — Model Platform（9F-1～9F-6）

## 目标

把 **Model ≠ ModelVersion**、**TrainingJob / TrainingRun**、**Artifact Bundle**、**Model Evaluation** 与 **可复现血缘** 纳入 Research Platform。

- **9F-1～9F-5**：Registry / Lineage / TrainingRun / Adapter / Artifact  
- **9F-6**：独立 `ModelEvaluationRun`（不可覆盖）+ Policy / Gate / IC·RankIC / Evaluation Artifact  

```text
ModelVersion
  → ModelEvaluationRequest
  → QualityGate → Predict → IC/RankIC/Ranking
  → ModelEvaluationResult
  → qd/artifacts/evaluation/{run_id}/
  ✕ PASS → ACTIVE / LIVE
  ✕ 指标写死在 ModelVersion 上
```

## 包位置

| 包 | 职责 |
| --- | --- |
| [`model_platform/`](../../../../backend_api_python/app/services/research_data/model_platform/) | 治理 + BundleStore + Loader |
| [`model_adapters/`](../../../../backend_api_python/app/services/research_data/model_adapters/) | Qlib 执行门面 |
| [`model_evaluation/`](../../../../backend_api_python/app/services/research_data/model_evaluation/) | **9F-6** 评估平台 |

`qd_model_platform@1` · `qd_model_evaluation@1`

## Model Evaluation（9F-6）

- `ModelEvaluationService.run_evaluation`（**不是** `ModelPlatformService.evaluate_model`）  
- Policy 预设 `MODEL_STANDARD_V1`  
- 结果分层：`quality` / `predictive` / `stability` / `ranking` / `overall`  
- 指标键与 9C/4D 语义对齐：`mean_ic` / `mean_rank_ic` / `ic_ir` / …  
- Artifact：`qd/artifacts/evaluation/{evaluation_run_id}/`  

边界：≠ 9C Factor Evaluation；≠ Backtest/Strategy；≠ 8C 生产审批。

## Artifact Bundle（9F-5）

```text
qd/artifacts/model/{artifact_id}/
```

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f_model_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f5_model_artifact.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f6_model_evaluation.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9f_model_platform.py \
  tests/research_data/test_phase9f3_training_run.py \
  tests/research_data/test_phase9f4_qlib_adapter.py \
  tests/research_data/test_phase9f5_model_artifact.py \
  tests/research_data/test_phase9f6_model_evaluation.py -q \
  --confcutdir=tests/research_data
```

保持 `verify_phase9e` 绿。

## Non-goals

```text
❌ 9F-7 Approval → ACTIVE 自动
❌ PASS → LIVE / Strategy
❌ Regime Engine / SHAP 产品化
❌ D1 存全量 prediction
```

## 后续

9F-7 Lifecycle & Approval · 9F-8 Repro · 9F-9 E2E
