# Phase 9F — Model Platform（9F-1～9F-4）

## 目标

把 **Model ≠ ModelVersion**、**TrainingJob / TrainingRun**、**Artifact** 与 **可复现血缘** 纳入 Research Platform，并经 **Model Adapter** 接合 Qlib 执行层。

- **9F-1**：契约与注册中心  
- **9F-2**：正式 ModelVersion 仅由成功训练创建；lineage / repro / active 查询  
- **9F-3**：TrainingJob + 完整 TrainingRun FSM + Stub Executor  
- **9F-4**：Model Adapter Contract + `QlibModelAdapter`（包装 Phase 2D `ModelTrainer`）

```text
TrainingJob
  → TrainingRun (QUEUED→PREPARING→RUNNING→FINALIZING→SUCCEEDED)
  → executor=stub|local → Stub
  → executor=qlib → QlibModelAdapter → ModelTrainer → ArtifactCandidate
  → create_version_from_run → ModelVersion (TRAINED)
  ✕ Qlib 类型泄漏进 Domain
  ✕ Model Evaluation / Strategy LIVE（→ 后续）
```

## 包位置

| 包 | 职责 |
| --- | --- |
| [`model_platform/`](../../../../backend_api_python/app/services/research_data/model_platform/) | 治理：Registry / Job / Run FSM / Lineage |
| [`model_adapters/`](../../../../backend_api_python/app/services/research_data/model_adapters/) | 执行门面：`TrainingContext` / Registry / `QlibModelAdapter` |

`model_platform/` **禁止**直接 `import qlib` / `model_training`；仅依赖 `model_adapters`。

`ENGINE_VERSION=qd_model_platform@1` · Adapter `qd_model_adapter@1`

## 与 Phase 2D

[`model_training/`](../../../../backend_api_python/app/services/research_data/model_training/) 仍是 LightGBM **执行核**。9F-4 Adapter 将其包装为：

```text
TrainingContext → ResearchDatasetSpec + ModelTrainSpec → ModelTrainer.train
  → ModelArtifactCandidate → create_version_from_run
```

数据入口：`dataset_ref` + DataQuery → Materializer → `QlibAdapter`（Qlib 不直连 R2）。

## Service API

```python
ModelPlatformService(
  store,
  registry=None,
  data_query=None,
  qlib_adapter=None,
  research_registry=None,
  train_artifact_store=None,
)

.submit_training_job / .execute_training_run / .retry_training_run / .cancel_training_run
.create_version_from_run / .register_model / .get_lineage / …
.predict(model_version_id, dataset_ref=..., segments=...)  # 薄；非 Signal
```

`resource_config.executor`: `stub`/`local`（默认）| `qlib`。

Job/Run 增加 `dataset_ref`；qlib 路径 PREPARING 校验 hash 一致性。

## TrainingRun FSM

```text
QUEUED → PREPARING | CANCELLED
PREPARING → RUNNING | FAILED
RUNNING → FINALIZING | FAILED | CANCELLED
FINALIZING → SUCCEEDED | FAILED
```

## Predict

`PredictionRequest` → `PredictionResult`（instrument / prediction）。**Prediction ≠ Signal**。

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f_model_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f4_qlib_adapter.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9f_model_platform.py \
  tests/research_data/test_phase9f3_training_run.py \
  tests/research_data/test_phase9f4_qlib_adapter.py -q \
  --confcutdir=tests/research_data
```

无 qlib/lightgbm 时 `verify_phase9f4` 仍验合同与 stub；真实训 skip。保持 `verify_phase9e` 绿。

## Non-goals

```text
❌ 9F-5 完整 R2 Artifact Store 产品化
❌ 9F-6 ModelEvaluation 实体
❌ XGBoost/CatBoost/PyTorch 实装（Registry 可扩展）
❌ Strategy / Signal / LIVE
❌ Qlib Recorder 替代 TrainingRun
```

## 后续

9F-5 Artifact Bundle · 9F-6 Evaluation · 9F-7 Approval · 9F-8 Repro · 9F-9 E2E
