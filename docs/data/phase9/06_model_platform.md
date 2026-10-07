# Phase 9F — Model Platform（9F-1～9F-8）

## 目标

把 **Model ≠ ModelVersion**、**TrainingJob / TrainingRun**、**Artifact Bundle**、**Model Evaluation**、**Approval / Activation** 与 **Reproducible Training** 纳入 Research Platform。

- **9F-1～9F-5**：Registry / Lineage / TrainingRun / Adapter / Artifact  
- **9F-6**：独立 `ModelEvaluationRun`  
- **9F-7**：`ModelApproval` / 单 `ACTIVE`  
- **9F-8**：TrainingRun 级 `ReproducibilityManifest` + `ReproducibilityRun`（不改源 Run）

```text
VALIDATED ≠ APPROVED ≠ ACTIVE
Model APPROVED ≠ Strategy VALIDATED ≠ Strategy LIVE
STRICT | REPRODUCIBLE | AUDITABLE
```

```text
TrainingRun
  → ReproducibilityManifest (+ Input / Env / Seeds)
  → ReproducibilityRun
  → NEW child TrainingRun (parent_training_run_id)
  → Compare → Report
  ✕ mutate 原 TrainingRun / ModelVersion
  ✕ 复现产物自动 Approval / ACTIVE / LIVE
```

## 包位置

| 包 | 职责 |
| --- | --- |
| [`model_platform/`](../../../../backend_api_python/app/services/research_data/model_platform/) | 治理 + Bundle + Approval |
| [`model_adapters/`](../../../../backend_api_python/app/services/research_data/model_adapters/) | Qlib 执行门面 |
| [`model_evaluation/`](../../../../backend_api_python/app/services/research_data/model_evaluation/) | **9F-6** 评估 |
| [`model_reproducibility/`](../../../../backend_api_python/app/services/research_data/model_reproducibility/) | **9F-8** 可复现 |

`qd_model_platform@1` · `qd_model_evaluation@1` · `qd_model_reproducibility@1`

## Reproducible Training（9F-8）

- `ReproducibilityService.capture_from_training_run` / `reproduce`  
- Policy：`REPRO_STRICT_V1` / `REPRO_NUMERICAL_V1` / `REPRO_AUDITABLE_V1`  
- 结果码：`EXACT_MATCH` / `NUMERICAL_MATCH` / `DATA_MISMATCH` / `INPUT_MISMATCH` / `CODE_MISMATCH` / `ENV_MISMATCH` / `DEPENDENCY_MISMATCH` / `SEED_MISMATCH` / `NON_DETERMINISTIC` / …  
- Artifact：`qd/artifacts/reproducibility/{repro_run_id}/`  
- Version tip `model_repro_manifest@1` 增加 `repro_manifest_id` 指针（向后兼容）

## Model Approval（9F-7）

- `approve_version` / `activate`（单 ACTIVE）；禁止裸 `transition(..., APPROVED)`

## Model Evaluation（9F-6）

- `ModelEvaluationService.run_evaluation`（**不是** `evaluate_model`）

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f_model_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f5_model_artifact.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f6_model_evaluation.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f7_model_approval.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f8_model_reproducibility.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9f_model_platform.py \
  tests/research_data/test_phase9f5_model_artifact.py \
  tests/research_data/test_phase9f6_model_evaluation.py \
  tests/research_data/test_phase9f7_model_approval.py \
  tests/research_data/test_phase9f8_model_reproducibility.py -q \
  --confcutdir=tests/research_data
```

保持 `verify_phase9e` / `9f7` / `9f6` / `9f5` 绿。

## Non-goals

```text
❌ 改写原 TrainingRun / ModelVersion
❌ 复现 → 自动 Evaluation / Approval / ACTIVE / LIVE
❌ 真实 Docker 重建 / 强制本机 uv.lock
❌ GPU bit-identical 保证
❌ HTTP Admin UI / D1 必过 Verify
```

## 后续

9F-9 E2E Acceptance & Hardening
