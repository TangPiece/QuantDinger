# Phase 9A — Research Dataset Platform

## 目标

把 Registry 中的 `DatasetDefinition` 与 R2/本地 **def.json + manifest.json** 闭环，使 `DatasetHandle.manifest_uri` 非空且不可变发布可审计。

```text
DatasetDefinition
  → DatasetQualityGate
  → DatasetBuilder (snapshot + registry)
  → def.json + DatasetManifest
  → DatasetHandle (dataset_hash + manifest_uri)
  → DataQuery.dataset / Qlib Materializer（消费者不变）
```

## 包位置

`backend_api_python/app/services/research_data/dataset_platform/`

| 模块 | 职责 |
| --- | --- |
| `protocol.py` | `ENGINE_VERSION=qd_dataset_platform@1`、`DatasetManifest` |
| `identity.py` / `pin.py` | 引用解析、manifest 组装 |
| `hashing.py` | 薄封装 `research_data.hashing`（`materializer_version="none"`） |
| `quality_gate.py` | universe / features / snapshot / PIT / price_policy / checksum |
| `immutability.py` | 同 `(code, version, snapshot_id)` 拒绝覆盖 |
| `builder.py` / `writers.py` / `artifact_store.py` | 写 def.json + manifest.json |
| `runner.py` | `ResearchDatasetService` 门面 |

## Service API

```python
ResearchDatasetService(store, registry, *, query=None)

.build_and_register(definition, *, snapshot_items, inject=None) -> DatasetHandle
.get(dataset_ref) -> DatasetHandle
.get_manifest(dataset_ref) -> DatasetManifest
.assert_immutable(dataset_ref)
.list_datasets(code_prefix=None)
```

## R2 布局（与 Phase 1 一致）

```text
qd/dataset/{code}/{version}/def.json
qd/dataset/{code}/{version}/{snapshot_id}/manifest.json
```

Registry `get_dataset` 填充 `manifest_uri`（LocalJson 可存 `_manifest_uri`；D1 默认 compute-on-read 为 `r2://…/manifest.json`）。

## Hash（锁死）

```text
dataset_hash = SHA256(
  definition | version | snapshot_id | schema_version
  | processor | materializer_version="none" | price_policy
)
```

## Non-goals（9A）

```text
❌ Factor / Model / Experiment orchestration (9B+)
❌ 修改 domain dataset_hash 算法
❌ 替换 DefaultQlibMaterializer / qlib-cache 迁 R2
❌ Research Flask UI
❌ Trading DB / OMS
❌ 默认 D1 0039 迁移（可选后续仅缓存 manifest_uri 列）
```

## 验收

- `scripts/verify_phase9a_dataset_platform.py`
- `tests/research_data/test_phase9a_dataset_platform.py`
