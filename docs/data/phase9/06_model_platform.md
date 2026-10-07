# Phase 9F — Model Platform（9F-1～9F-9 **Done**）

## 目标

把 **Model ≠ ModelVersion**、Training、Artifact、Evaluation、Approval、Activation、Reproducibility 串成可长期运行的 Model Platform，并以 **9F-9 E2E Hardening** 收口。

```text
Dataset → Feature/Label → TrainingRun → Artifact → ModelVersion
  → Evaluation → Approval → Activation
  → Reproducibility
  ✕ Model ACTIVE ≠ Strategy LIVE
  ✕ Flask（契约以 Service 为准；HTTP → 9H）
```

`qd_model_platform@1` · `qd_model_evaluation@1` · `qd_model_reproducibility@1`

## 包

| 包 | 阶段 |
| --- | --- |
| [`model_platform/`](../../../../backend_api_python/app/services/research_data/model_platform/) | 9F-1～5, 7, 9 lineage |
| [`model_adapters/`](../../../../backend_api_python/app/services/research_data/model_adapters/) | 9F-4 |
| [`model_evaluation/`](../../../../backend_api_python/app/services/research_data/model_evaluation/) | 9F-6 |
| [`model_reproducibility/`](../../../../backend_api_python/app/services/research_data/model_reproducibility/) | 9F-8 |

## 9F-9 E2E & Hardening

- `ModelPlatformService.get_full_lineage`：一键树（Model / Run / Artifact / Eval / Approval / Activation / Repro）  
- `activate`：按 `model_id` 进程锁 + Artifact AVAILABLE 门控 + 单 ACTIVE  
- Orchestrator：[`verify_phase9f9_model_platform_e2e.py`](../../../../backend_api_python/scripts/verify_phase9f9_model_platform_e2e.py)  
- Hardening：`phase9f_hardening/` · Golden：`phase9f_lifecycle_golden/`  
- 平面扫描：[`scan_phase9f_plane_isolation.py`](../../../../backend_api_python/scripts/scan_phase9f_plane_isolation.py)

### Done Criteria（8）

1. 完整 Model Lifecycle E2E  
2. TrainingRun ↔ Version ↔ Artifact 绑定  
3. Evaluation → Approval → Activation 不可绕过；ACTIVE ≠ Strategy LIVE  
4. Dataset / Code / Env / Dep / Seed 可追溯  
5. 历史对象不可变 + 禁删  
6. Reproduce → EXACT / NUMERICAL_MATCH  
7. 故障注入 + Job 幂等 + 并发 activate  
8. Active Version → `get_full_lineage`

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9f9_model_platform_e2e.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9f9_model_platform_e2e.py -q \
  --confcutdir=tests/research_data
```

保持 `verify_phase9e` 绿（由 9F-9 orchestrator 回归）。

## Non-goals

```text
❌ Flask / Admin UI
❌ D1 唯一索引落地（文档可选未来）
❌ Strategy Candidate / Promotion / Shadow / LIVE / OMS
❌ 物理 DELETE 历史对象
```

## 后续

**Phase 9G — Research Experiment Platform**（实验编排 / 对比 / Ranking → Strategy Candidate）
