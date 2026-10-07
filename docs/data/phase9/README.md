# Phase 9 — Research Platform Roadmap

Phase 9 在既有 `research_data` Domain（Definition / Snapshot / `dataset_hash` / Qlib 派生物化）之上，补齐研究平台能力。**Domain hash 算法与 Qlib materializer 派生层不在本阶段改动。**

| 子阶段 | 主题 | 状态 |
| --- | --- | --- |
| **9A** | Research Dataset Platform（manifest + builder + gate + immutability） | **Done** — [01_dataset_platform.md](01_dataset_platform.md) |
| **9B** | Feature / Factor Platform（taxonomy + FeatureSet + build + lineage） | **Done** — [02_feature_factor_platform.md](02_feature_factor_platform.md) |
| **9C** | Factor Evaluation Engine（Policy + Run + 4C–4F 编排） | **Done** — [03_factor_evaluation_engine.md](03_factor_evaluation_engine.md) |
| **9D** | Factor Mining（DSL 模板搜索 + Screen + 9C） | **Done** — [04_factor_mining.md](04_factor_mining.md) |
| **9E** | Factor Library / Portfolio（Promotion Gate + Catalog + Collection） | **Done** — [05_factor_library.md](05_factor_library.md) |
| 9F | Model Platform | Planned |
| 9G | Experiment Orchestration | Planned |
| 9H | Research UI / API 管理台 | Planned |
| 9I | Cross-cutting governance | Planned |
| 9J | E2E / hardening | Planned |

## 9A 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9a_dataset_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9a_dataset_platform.py -q --confcutdir=tests/research_data
```

## 9B 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9b_feature_factor_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9b_feature_factor_platform.py -q --confcutdir=tests/research_data
```

## 9C 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9c_factor_evaluation.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9c_factor_evaluation.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9b_feature_factor_platform.py` 绿。

## 9D 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9d_factor_mining.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9d_factor_mining.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9c_factor_evaluation.py` 绿。

## 9E 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9e_factor_library.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9e_factor_library.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9c_factor_evaluation.py` 与 `verify_phase9d_factor_mining.py` 绿。

## 边界（全 Phase 9 共享）

- 子包位于 `app/services/research_data/*`，**不**新建顶层 Domain。
- `compute_dataset_hash` 输入集锁死；Qlib 仍用 `materialization_id = SHA256(dataset_hash | qlib_materializer@1)`。
- 无 Trading DB / OMS 读取；无默认实盘下单编排。
