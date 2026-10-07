# Phase 8E — Live Performance Feedback

## 目标

建立 **Research Expected → Production Actual → Deviation Analysis**，回答「晋级后是否仍符合研究预期？」——**不**重做 Backtest，**不**自动停 LIVE。

```text
Promotion COMPLETED
  → freeze ExpectedBaseline (immutable)
  → collect Actual (Shadow / CL / Live artifacts)
  → PerformanceComparisonRun
  → Drift Classification + Attribution
  → ProductionDriftReport
  ✕ mutate StrategyVersion / auto demote
```

## 边界

**做（P0）**

- 包 `backend_api_python/app/services/live_performance_feedback/`
- `ExpectedBaseline`：8D `COMPLETED` 后冻结；含 lineage + metrics 快照；**immutable**
- `PerformanceComparisonRun`：对比 baseline vs `SHADOW` / `CONTROLLED_LIVE` / `LIVE`
- 六类指标 + Fake inject；可选读 7B/7C compare 索引（不替换 7B/7C 服务）
- `DriftPolicy`（`default_drift_v1`）→ ALERT 建议，**不改环境**
- D1 `0035` + R2 `qd/registry/performance_feedback/...`
- 8D execute 完成后可选 `freeze_baseline_from_promotion`（失败不回滚 promotion）

**不做**

```text
❌ Auto demote / stop LIVE
❌ Mutate StrategyVersion / rebaseline via fresh backtest
❌ Replace 7B/7C compare services
❌ Full realtime monitoring dashboard (8F)
❌ OMS submit
```

## 包结构

```text
live_performance_feedback/
  protocol.py              # ENGINE_VERSION=qd_live_performance_feedback@1
  identity.py / pin.py / policy.py / policy_presets.py
  fsm.py / baseline.py
  collectors/              # shadow_compare, cl_compare, metrics_inject
  compare.py / attribution.py / report.py
  bridge_from_promotion.py
  writers.py / artifact_store.py / runner.py
```

## API

`LivePerformanceFeedbackService(store, registry, *, promotion=None)`：

- `freeze_baseline_from_promotion(pipeline_run_id, metrics_inject=None)` → `ExpectedBaseline`
- `run_comparison(baseline_id, actual_source, window_*, idempotency_key, inject=None)` → `PerformanceComparisonRun`
- `get_baseline` / `get_run` / `list_runs` / `get_report`
- `latest_drift_scalars(strategy_code)` — 供 8D precondition inject 只读

## 存储

- D1：`workers/qd-research-d1/migrations/0035_live_performance_feedback.sql`
  - `drift_policy` / `performance_expected_baseline` / `performance_comparison_run`
- R2：`qd/registry/performance_feedback/{strategy_code}/baselines|runs/{id}.json`

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8e_performance_feedback.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8e_performance_feedback.py -q --confcutdir=tests/research_data
```
