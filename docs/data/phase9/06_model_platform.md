# Phase 9F — Model Platform（9F-1～9F-7）

## 目标

把 **Model ≠ ModelVersion**、**TrainingJob / TrainingRun**、**Artifact Bundle**、**Model Evaluation**、**Approval / Activation** 与 **可复现血缘** 纳入 Research Platform。

- **9F-1～9F-5**：Registry / Lineage / TrainingRun / Adapter / Artifact  
- **9F-6**：独立 `ModelEvaluationRun`（不可覆盖）+ Policy / Gate / IC·RankIC / Evaluation Artifact  
- **9F-7**：`ModelApproval` / `ApprovalGate` / 单 `ACTIVE` + `ActivationRecord`

```text
VALIDATED ≠ APPROVED ≠ ACTIVE
Model APPROVED ≠ Strategy VALIDATED ≠ Strategy LIVE
```

```text
ModelVersion
  → ModelEvaluationRun (9F-6)
  → ApprovalGate (须 SUCCEEDED + overall PASS + Artifact AVAILABLE)
  → ModelApproval(APPROVED|REJECTED|REVOKED) 不可变追加
  → lifecycle APPROVED
  → activate → 唯一 ACTIVE + ActivationRecord
  ✕ APPROVED → 自动 ACTIVE
  ✕ Model APPROVED → Strategy LIVE
```

## 包位置

| 包 | 职责 |
| --- | --- |
| [`model_platform/`](../../../../backend_api_python/app/services/research_data/model_platform/) | 治理 + BundleStore + Loader + **Approval** |
| [`model_adapters/`](../../../../backend_api_python/app/services/research_data/model_adapters/) | Qlib 执行门面 |
| [`model_evaluation/`](../../../../backend_api_python/app/services/research_data/model_evaluation/) | **9F-6** 评估平台 |

`qd_model_platform@1` · `qd_model_evaluation@1`

## Model Approval（9F-7）

- `ModelPlatformService.validate_version` / `approve_version` / `revoke_approval` / `activate`  
- Policy 预设 `MODEL_APPROVAL_V1`（WARNING overall 默认不可批）  
- **禁止**裸 `transition(..., APPROVED)`；仅 `approve_version`（或 inject `skip_approval_gate` 单测）  
- `activate`：同 `model_id` 其他 ACTIVE → `DEPRECATED(NEW_VERSION)`；写 `ModelActivationRecord`  
- `usage_scope` 默认 `RESEARCH|EXPERIMENT|BACKTEST`（**无**自动 PRODUCTION 交易权）

边界：≠ Strategy Lifecycle；≠ OMS / LIVE；≠ 8C 生产审批。

## Model Evaluation（9F-6）

- `ModelEvaluationService.run_evaluation`（**不是** `ModelPlatformService.evaluate_model`）  
- Policy 预设 `MODEL_STANDARD_V1`  
- Artifact：`qd/artifacts/evaluation/{evaluation_run_id}/`

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
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f7_model_approval.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9f_model_platform.py \
  tests/research_data/test_phase9f3_training_run.py \
  tests/research_data/test_phase9f4_qlib_adapter.py \
  tests/research_data/test_phase9f5_model_artifact.py \
  tests/research_data/test_phase9f6_model_evaluation.py \
  tests/research_data/test_phase9f7_model_approval.py -q \
  --confcutdir=tests/research_data
```

保持 `verify_phase9e` / `verify_phase9f6` / `verify_phase9f5` 绿。

## Non-goals

```text
❌ APPROVED → 自动 ACTIVE
❌ Model APPROVED → Strategy LIVE / promote_strategy / OMS
❌ 无 Evaluation 的人工直批（无 ApprovalException 产品化特批）
❌ 删除 ModelVersion / Artifact
❌ HTTP Admin UI
❌ 改 Strategy Lifecycle
❌ Regime Engine / SHAP 产品化
```

## 后续

9F-8 Repro · 9F-9 E2E
