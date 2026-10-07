# Phase 9F — Model Platform（9F-1～9F-5）

## 目标

把 **Model ≠ ModelVersion**、**TrainingJob / TrainingRun**、**Artifact Bundle** 与 **可复现血缘** 纳入 Research Platform，并经 **Model Adapter** 接合 Qlib 执行层。

- **9F-1**：契约与注册中心  
- **9F-2**：正式 ModelVersion；lineage / repro  
- **9F-3**：TrainingJob + TrainingRun FSM + Stub Executor  
- **9F-4**：Model Adapter Contract + `QlibModelAdapter`  
- **9F-5**：Model Artifact Store（不可变 Bundle + checksum + Loader）

```text
TrainingRun → ArtifactCandidate → BundleStore.put → AVAILABLE
  → ModelVersion.artifact_id → Loader.verify/cache → Predict
```

## 包位置

| 包 | 职责 |
| --- | --- |
| [`model_platform/`](../../../../backend_api_python/app/services/research_data/model_platform/) | 治理 + BundleStore + Loader |
| [`model_adapters/`](../../../../backend_api_python/app/services/research_data/model_adapters/) | `TrainingContext` / Qlib 执行门面 |

`ENGINE_VERSION=qd_model_platform@1`

## Artifact Bundle（9F-5）

布局（`artifact_id` 为根）：

```text
qd/artifacts/model/{artifact_id}/
  model.bin
  manifest.json
  metadata.json
  feature_schema.json / processor.json / label_definition.json / environment.json
  checksum.sha256
```

索引：`qd/model_platform/artifacts/{id}.json`

状态机：`CREATING → UPLOADING → VERIFYING → AVAILABLE`（异常 `FAILED` / `CORRUPTED`）。  
AVAILABLE 后禁止覆盖同 id 内容；绑定 ModelVersion 后 `delete_artifact` 拒绝。

Loader 缓存：`qd/cache/models/{artifact_id}/`（checksum 命中复用）。

## Service API（增量）

```python
.put_model_artifact(payload, *, training_run_id=...) -> ModelArtifact
.verify_artifact / .load_model_artifact / .delete_artifact
.predict(...)  # 经 Loader verify
```

`execute_training_run` FINALIZING：stub/qlib payload → `put_model_artifact` → `create_version_from_run(artifact_id=…)`。

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f_model_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f4_qlib_adapter.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f5_model_artifact.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9f_model_platform.py \
  tests/research_data/test_phase9f3_training_run.py \
  tests/research_data/test_phase9f4_qlib_adapter.py \
  tests/research_data/test_phase9f5_model_artifact.py -q \
  --confcutdir=tests/research_data
```

保持 `verify_phase9e` 绿。

## Non-goals

```text
❌ 9F-6 ModelEvaluation
❌ 任意上传 model.bin → ACTIVE
❌ Evaluation/Dataset Artifact 全类型
❌ 物理硬删已绑定 Artifact
```

## 后续

9F-6 Evaluation · 9F-7 Approval · 9F-8 Repro · 9F-9 E2E
