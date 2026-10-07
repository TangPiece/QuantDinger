# Phase 9B — Feature / Factor Platform

## 目标

在 9A `DatasetHandle` 之上建立 Feature → Factor → Alpha（定义层）编排，发布不可变构建索引与 `factor_hash` / `feature_set_hash`，**不做**因子挖掘（9D）与完整 IC 评价编排（9C）。

```text
9A DatasetHandle (pinned)
  → Feature / Factor Registry + DAG + FeatureSet
  → Factor Pipeline 元数据（definition sidecar）
  → build_factor / build_feature_set → Parquet + build_index.json
  → DataQuery / Research 消费者
  ✕ Factor Mining / evaluate_ic 门面 / OMS
```

## 包位置

`backend_api_python/app/services/research_data/feature_factor_platform/`

| 模块 | 职责 |
| --- | --- |
| `taxonomy.py` | `FEATURE` / `FACTOR` / `ALPHA` 分层（旧 4A 默认 `FACTOR`） |
| `feature_set.py` / `pipeline.py` | FeatureSet 与 FactorPipelineSpec |
| `quality_gate.py` | PIT、依赖、9A manifest、pipeline 字段 |
| `builders.py` | 复用 `FactorComputeService`，钉住 `dataset_hash` |
| `lineage.py` | 正向血缘 + `list_by_dataset` |
| `runner.py` | `FeatureFactorService` 门面 |

## Service API

```python
FeatureFactorService(store, registry, *, query=None, dataset_svc=None, compute=None)

.register_feature(def) / .register_factor(def, pipeline=None) / .register_alpha(alpha)
.register_feature_set(FeatureSetDefinition) -> FeatureSetManifest
.build_factor(factor_ref, dataset_ref, *, window, layout="long", inject=None)
.build_feature_set(feature_set_ref, dataset_ref, *, window, layout="long", inject=None)
.get_lineage(ref, *, dataset_ref=None) / .list_by_dataset(dataset_hash)
.get_manifest(feature_set_ref) / .assert_immutable(feature_set_ref)
```

**无** `mine_factors` / `evaluate_ic` / `train_model` / `promote`。

## Hash

- **Factor**：`factor_lab.hash.compute_factor_hash`；非空 `definition`（pipeline / asset_kind）参与 payload，空 `{}` 保持 4A 兼容。
- **FeatureSet**：`SHA256(sorted member_refs + processor + schema + ENGINE_VERSION)`。
- **Dataset**：仍 9A `compute_dataset_hash`。

`ENGINE_VERSION=qd_feature_factor_platform@1`

## Non-goals（9B）

```text
❌ Factor mining / GP / Symbolic Regression
❌ Full IC/Decile evaluation orchestration (9C)
❌ Qlib 内部 Feature 系统改写
❌ Signal / live trading / OMS
❌ 默认 D1 新表（FeatureSet → LocalJson + manifest）
```

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9b_feature_factor_platform.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9b_feature_factor_platform.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9a_dataset_platform.py` 绿。
