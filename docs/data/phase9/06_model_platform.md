# Phase 9F — Model Platform（9F-1～9F-3）

## 目标

把 **Model ≠ ModelVersion**、**TrainingJob / TrainingRun**、**Artifact** 与 **可复现血缘** 纳入 Research Platform。

- **9F-1**：契约与注册中心  
- **9F-2**：正式 ModelVersion 仅由成功训练创建；lineage / repro / active 查询  
- **9F-3**：TrainingJob + 完整 TrainingRun FSM + Stub Executor（**不**接 Qlib）

**不**调用 `ModelTrainer` / Qlib、不评价模型、不接 Strategy LIVE。

```text
TrainingJob
  → TrainingRun (QUEUED→PREPARING→RUNNING→FINALIZING→SUCCEEDED)
  → create_version_from_run
  → ModelVersion (TRAINED)
       ├── ModelArtifact
       └── model_repro_manifest.json
  ✕ 原地改 FAILED run 重跑（须 retry → 新 Run）
  ✕ Qlib Adapter / ModelTrainer（→ 9F-4）
  ✕ Model Evaluation / Strategy LIVE
```

## 包位置

`backend_api_python/app/services/research_data/model_platform/`

| 模块 | 职责 |
| --- | --- |
| `protocol.py` | Model / ModelVersion / TrainingRun / ModelArtifact |
| `lifecycle.py` | FSM：`DRAFT→…→ACTIVE→DEPRECATED→RETIRED` |
| `lineage.py` | 正式创建血缘校验 + `get_lineage` 视图 |
| `repro.py` | `model_repro_manifest.json` |
| `prepare_gate.py` / `executor.py` | PREPARING 门控 + Stub 编排 |
| `job.py` / `training_config.py` | TrainingJob / TrainingConfig hash |
| `immutability.py` | TrainingRun FSM + Version lineage 硬化 |
| `catalog.py` / `search.py` | 注册与检索 |
| `hashing.py` | config / version / training_run hash |
| `bridge_legacy.py` | → Phase 2D `ModelDefinition` / `ModelVersionRecord` |
| `runner.py` | `ModelPlatformService` |

`ENGINE_VERSION=qd_model_platform@1`

## 与 Phase 2D

[`model_training/`](../../../../backend_api_python/app/services/research_data/model_training/) 仍是 LightGBM **执行层**。9F 是 **治理/注册层**。9F-4 再接 Qlib Adapter。

## Service API

```python
ModelPlatformService(store, registry=None)

.register_model / .get_model / .search
.register_version  # 须 SUCCEEDED/FINALIZING run，或 inject.allow_draft_stub
.create_version_from_run(...)
.submit_training_job / .get_job / .list_runs_for_job
.execute_training_run / .retry_training_run / .cancel_training_run
.update_training_run_status / .create_training_run / .get_training_run
.get_version / .list_versions / .get_active_version
.get_lineage / .get_artifact_for_version / .get_repro_manifest
.activate / .deprecate / .retire / .transition
.delete_version  # 永远拒绝
```

**无** `train` / `predict` / `evaluate_model` / `auto_live` / `promote_strategy`。

## TrainingRun FSM（9F-3）

```text
QUEUED → PREPARING | CANCELLED
PREPARING → RUNNING | FAILED
RUNNING → FINALIZING | FAILED | CANCELLED
FINALIZING → SUCCEEDED | FAILED
SUCCEEDED / FAILED / CANCELLED → ∅
```

PREPARING 校验 dataset/feature/label/snapshot；失败分类如 `DATA_MISSING`。  
Retry：`retry_training_run` 新建 Run（`parent_training_run_id`），禁止改写父 Run。

## ModelVersion Lifecycle

```text
DRAFT → TRAINING → TRAINED → EVALUATING → VALIDATED
  → APPROVED → ACTIVE → DEPRECATED → RETIRED
```

正式路径从 `TRAINED` 起步。**Model ACTIVE ≠ Strategy LIVE。**

## D1

Migration [`0039_model_platform.sql`](../../../../workers/qd-research-d1/migrations/0039_model_platform.sql)。  
**Verify 路径以 LocalJson 为 SSOT**，不依赖 D1。

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f_model_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9f_model_platform.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9e_factor_library.py` 绿。

## Non-goals

```text
❌ Qlib Adapter / train execution（→ 9F-4）
❌ Model Evaluation metrics（→ 9F-6）
❌ Auto Strategy / LIVE
❌ Replace Phase 2D ModelTrainer
❌ Delete formal ModelVersion
```

## 后续子阶段（未实现）

9F-4 Qlib Adapter · 9F-5 Artifact Bundle · 9F-6 Evaluation · 9F-7 Approval · 9F-8 Repro 闭环 · 9F-9 E2E
