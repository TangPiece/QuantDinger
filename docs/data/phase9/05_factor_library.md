# Phase 9E — Factor Library / Factor Portfolio

## 目标

将 9D Candidate + 9C Evaluation 沉淀为**可检索、可组合、可去冗余**的 Factor Library；**Collection**（集合）与 **PortfolioSpec**（加权组合定义）分离；**不**直连 Production / LIVE。

```text
FactorCandidate / DRAFT (9B/9D)
  → Promotion Gate (9C SUCCESS + gate PASS)
  → FactorLibraryEntry (APPROVED → ACTIVE)
  → Search / Tags / Taxonomy
  → Similarity + Cluster (4H corr 矩阵注入或薄封装)
  → FactorCollection | FactorPortfolioSpec (versioned hash)
  → consume: 9B FeatureSet / 4H combine / 4I portfolio run
  ✕ auto Strategy / LIVE / MV optimizer
```

## 包位置

`backend_api_python/app/services/research_data/factor_library_platform/`

| 模块 | 职责 |
| --- | --- |
| `lifecycle.py` | FSM：`DRAFT→…→ACTIVE→DEPRECATED→RETIRED` |
| `promotion.py` | Promotion Gate（9C `SUCCESS` + `gate_verdict=PASS`） |
| `catalog.py` / `search.py` | LibraryEntry 索引与检索 |
| `similarity.py` / `cluster.py` | 相关/similarity；阈值连通分量聚类 |
| `collection.py` / `portfolio_spec.py` / `weights.py` | 集合 vs 组合；EQUAL/ICIR/RISK/CORR_ADJUSTED |
| `bridge_featureset.py` | `to_feature_set` → 9B `FeatureSetDefinition` |
| `runner.py` | `FactorLibraryService` 门面 |

`ENGINE_VERSION=qd_factor_library_platform@1`

## Service API

```python
FactorLibraryService(store, registry, *,
    factor_svc=None, eval_svc=None, mining_svc=None)

.promote_to_library(*, candidate_id=None, factor_ref=None, evaluation_id=None, operator="")
.activate(entry_id) / .deprecate(entry_id, reason, replacement_ref="") / .retire(entry_id)
.search(FactorSearchQuery) -> list[LibraryEntry]
.similar_factors(factor_ref, top_k=10)
.build_cluster(factor_refs, *, policy) -> FactorCluster
.create_collection / .get_collection
.create_portfolio_spec / .get_portfolio_spec / .resolve_weights(portfolio_id)
.list_usages(factor_ref)
.to_feature_set(collection_id | portfolio_id, code, version) -> FeatureSetDefinition
```

**无** `auto_live` / `optimize_mv` / `promote_strategy` / Mean-Variance / Risk Parity。

## Hash

- `collection_hash = SHA256(sorted member_refs + version)`
- `portfolio_spec_hash = SHA256(members/collection + weight_method + weights + version)`
- `cluster_hash = SHA256(members + method + threshold + dataset_hash + policy_version)`

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase9e_factor_library.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase9e_factor_library.py -q --confcutdir=tests/research_data
```

并保持 `verify_phase9c_factor_evaluation.py` 与 `verify_phase9d_factor_mining.py` 绿。

## Non-goals

- MV / risk parity optimizers
- Auto production strategy / LIVE
- 替换 4H/4I 执行层数学
- 删除 RETIRED factor 物理数据
- Model Platform（→ **9F**）
