# Phase 9F — Model Platform（9F-1：Contract & Registry）

## 目标

把 **Model ≠ ModelVersion**、**TrainingRun 不可变**、**Artifact 自描述索引** 纳入 Research Platform；本子阶段只做契约与注册中心，**不**执行训练、不评价模型、不接 Strategy LIVE。

```text
Model
  → ModelVersion (lineage hashes + lifecycle)
       ├── TrainingRun (pin only)
       └── ModelArtifact (index only)
  ✕ Qlib Adapter / ModelTrainer
  ✕ Model Evaluation
  ✕ Strategy Candidate / LIVE
```

## 包位置

`backend_api_python/app/services/research_data/model_platform/`

| 模块 | 职责 |
| --- | --- |
| `protocol.py` | Model / ModelVersion / TrainingRun / ModelArtifact |
| `lifecycle.py` | FSM：`DRAFT→…→ACTIVE→DEPRECATED→RETIRED` |
| `catalog.py` / `search.py` | 注册与检索 |
| `hashing.py` | `model_config_hash` / `version_content_hash` / `training_run_hash` |
| `bridge_legacy.py` | → Phase 2D `ModelDefinition` / `ModelVersionRecord` |
| `runner.py` | `ModelPlatformService` |

`ENGINE_VERSION=qd_model_platform@1`

## 与 Phase 2D

[`model_training/`](../../../../backend_api_python/app/services/research_data/model_training/) 仍是 LightGBM **执行层**。9F 是 **治理/注册层**。9F-4 再接 Qlib Adapter。

## Service API

```python
ModelPlatformService(store, registry=None)

.register_model / .get_model / .search
.register_version / .get_version / .list_versions
.create_training_run / .get_training_run   # pin only
.register_artifact / .get_artifact
.activate / .deprecate / .retire / .transition
.compute_model_config_hash(config) -> str
.to_legacy_definition / .to_legacy_version_record
```

**无** `train` / `predict` / `evaluate_model` / `auto_live` / `promote_strategy`。

## Lifecycle

```text
DRAFT → TRAINING → TRAINED → EVALUATING → VALIDATED
  → APPROVED → ACTIVE → DEPRECATED → RETIRED
```

**Model ACTIVE ≠ Strategy LIVE。**

## D1

Migration [`0039_model_platform.sql`](../../../../workers/qd-research-d1/migrations/0039_model_platform.sql)：扩展 `model` / `model_version` / `artifact`，新增 `training_run`。  
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
❌ Delete retired model bytes
```

## 后续子阶段（未实现）

9F-2 Lineage 深化 · 9F-3 TrainingRun 执行编排 · 9F-4 Qlib Adapter · 9F-5 Artifact Bundle · 9F-6 Evaluation · 9F-7 Approval · 9F-8 Repro · 9F-9 E2E
