# Phase 8H — Production → Research Feedback Loop

## 目标

> 把 8E/8F/8G 生产工件**安全、可追溯**地重新进入 Qlib Research（仅 DataQuery / Registry 路径）。

```text
8E/8F/8G artifacts (+ Fake inject)
  → Feedback Builder
  → FeedbackQualityGate (PIT / completeness / lineage)
  → ProductionFeedbackDataset + ProductionRealitySnapshot + ResearchFailureCase (immutable)
  → ResearchFeedbackQuery / DataQuery.production_feedback
  → ResearchHypothesis → Experiment (parent_* lineage)
  → (人工) Candidate → 8C Validation → …
  ✕ auto train / mutate ModelVersion / StrategyVersion
  ✕ bypass Validation / Promotion
  ✕ Qlib → Trading DB / OMS
```

Actual vs Counterfactual **严格隔离**（`reality_kind=ACTUAL|COUNTERFACTUAL`）；Counterfactual 永不写入 Actual PnL。

## 包结构

```text
production_research_feedback/
  protocol.py              # ENGINE_VERSION=qd_production_research_feedback@1
  identity.py, pin.py, hashing.py
  quality_gate.py, builder.py
  collectors/              # from_feedback_8e, from_monitoring_8f, from_guardrails_8g, inject
  bridges/
  query.py, hypothesis.py, experiment_link.py, counterfactual.py
  adapter_dataquery.py
  writers.py, artifact_store.py, runner.py
```

## Service API

`ProductionResearchFeedbackService(store, registry, *, feedback_8e=None, monitoring=None, guardrails=None, data_query=None)`：

- `build_dataset` / `build_reality_snapshot` / `record_failure_case`
- `query_feedback` / `get_dataset` / `get_snapshot` / `list_failure_cases`
- `create_hypothesis` / `link_experiment`
- `build_counterfactual`

**无** `train_model` / `mutate_version` / `promote` / `submit_order`

## 存储

- D1：`workers/qd-research-d1/migrations/0038_production_research_feedback.sql`
- R2：`qd/registry/production_research_feedback/{strategy_code}/datasets|snapshots|cases/...`

Snapshot **不可覆盖**；修正 → 新版本 + `supersedes_snapshot_id`。

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8h_production_research_feedback.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase8h_production_research_feedback.py -q --confcutdir=tests/research_data
```

Phase 8G verify 仍应绿。

## Non-goals

```text
❌ Auto train / replace Model or Strategy from feedback
❌ Qlib reads Trading DB
❌ Overwrite immutable snapshots
❌ Mix counterfactual into actual PnL
❌ Skip Validation / Promotion
```
