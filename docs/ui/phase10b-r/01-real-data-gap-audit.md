# 10B-R：Real Data Gap Audit（本地源码 SSOT）

> 状态：COMPLETE（以 `backend_api_python/app` 实际源码为准，非架构臆测）  
> 原则：不 Mock、不 INSERT 造研究资产、不用 Golden/fixture 冒充生产数据。

## 状态枚举

`EXISTS` | `PARTIAL` | `MISSING` | `BROKEN` | `NO_UI` | `NO_API`

## 全层矩阵（摘要）

| 环节 | Domain / Service | Job | Write HTTP | Read HTTP | UI | 状态 |
|------|------------------|-----|------------|-----------|-----|------|
| Canonical Store / Writer | Partial store/writer/paths | 脚本/ingest | 无产品 API | 间接 | NO_UI | PARTIAL |
| Market → Canonical | 有写入路径，生产验收未锁 | 脚本 | NO_API | — | NO_UI | PARTIAL |
| Universe → Canonical Snapshot | Universe snapshot 能力存在 | — | — | — | — | EXISTS |
| Research Registry | LocalJson + D1 | — | — | 经 query | — | EXISTS |
| DatasetBuilder | `ResearchDatasetService.build_and_register` 存在；缺产品 Snapshot Assembler | 无 worker | NO_API | EXISTS GET datasets | 只读 | PARTIAL |
| Dataset Read API | research_query DTO | — | — | EXISTS | List/Detail | EXISTS |
| Feature / Factor Service | feature_factor_platform + compute | 无 | NO_API | PARTIAL features/alpha GET | Factor 只读 | PARTIAL |
| FeatureSet | Domain/Service 有 | 无 | NO_API | NO_API | NO_UI | NO_API |
| Factor Evaluation | 9C `run_evaluation` → Summary 真实 | 无 | NO_API | GET evaluation | Detail 可展示 | NO_API（触发） |
| Mining | MiningService 有 | 进程内 | NO_API | — | ComingSoon | NO_API |
| Library / Portfolio | promote gated / portfolio service | 无 | NO_API | GET list | NO_UI | NO_API |
| Model Platform | 9F train→artifact→approve 在进程内 | 进程内 Job | NO_API | PARTIAL models | 只读 | PARTIAL |
| Model Read Bridge | ModelPlatform cache ≠ ResearchRegistry artifact | — | — | BROKEN | — | BROKEN |
| Artifact Read Bridge | `GET /artifacts/:id` → Registry；Model 写 ModelArtifactStore | — | — | BROKEN | NO_UI | BROKEN |
| Model Evaluation Read | 真 `ModelEvaluationService` vs API 只回 version.metrics | — | — | BROKEN | NO_UI | BROKEN |
| Experiment | register → status=`COMPLETED`，无 Run | MISSING | POST（假） | GET | 有登记 | BROKEN |
| Product Status | research_query.product_status | — | — | EXISTS | Dashboard | EXISTS |

## 关键源码结论

### 1. Dataset 不是「表单字段 → build」

真实依赖：

```text
DatasetDefinition + snapshot_items
  → DatasetBuilder
  → create_snapshot()
  → write_dataset_artifacts()
  → upsert_dataset()
```

D1 `create_snapshot()` 要求 item 含 `data_version_id`，但 Registry **缺少**统一 `list_data_versions(...)` Discovery API。  
因此 R1 缺口是：**Canonical → Discovery → Snapshot Assembler → snapshot_items**，不是单纯加 `POST /datasets/build`。

### 2. Golden 禁止作为产品数据

`build_golden.py` 路径含 `use_fixture=True`、synthetic PIT/CA、fixture universe/market。  
**禁止** Golden → Dataset → UI 冒充生产。

### 3. Model 双事实源

- `ModelPlatformService` hydrate：`~/.quantdinger/cache/qd/model_platform`（及 ModelArtifactStore）
- Research Read Artifact：`ResearchRegistry.get_artifact()`
- `register_artifact()` 主要写 ModelArtifactStore，未形成统一 Research Registry → Platform → Read 链

### 4. Model Evaluation Read 语义错误

真链路：`ModelEvaluationService` → EvaluationRun → metrics/predictions/ranking/stability。  
现 `GET /api/research/models/:id/evaluation` 仅返回 `ModelVersion.metrics` + `lifecycle`。

### 5. Experiment 假完成

`POST /api/research/experiments` → `register_experiment()` → Registry + `status="COMPLETED"`，无 ExperimentRun / Job / Backtest / Artifact / Metrics。

## 证据锚点

- `app/routes/research_read.py`
- `app/services/research_data/dataset_platform/`
- `app/services/research_data/registry.py`（`upsert_data_version` / `create_snapshot`）
- `app/services/research_data/evaluation_platform/`
- `app/services/research_data/model_platform/`
- `app/services/research_data/model_evaluation/`
- `app/services/research_data/experiment_platform/`
- `app/services/research_data/research_query/`
- Phase 9 verify scripts under `backend_api_python/scripts/verify_phase9*.py`（输出多为 temp，≠ API cache）
