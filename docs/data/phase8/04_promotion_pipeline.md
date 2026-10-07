# Phase 8D — Strategy Promotion Pipeline

## 目标

将 **ValidationRun.PASSED** 的 Candidate 推进到 **SHADOW / CONTROLLED_LIVE / LIVE**，并留下独立审计（非 8B `strategy_candidate_promotion`）：

```text
Candidate + ValidationRun.PASSED
  → PromotionRequest (钉 validation_id + content_hash)
  → PreconditionCheck (policy@version)
  → REGISTERED → SHADOW → CONTROLLED_LIVE → LIVE (gated)
  → PromotionRunRecord (immutable)
  ✕ Auto LIVE / 跨级 / 改 Strategy Version / OMS
```

## 与 8B 的关系

| 类型 | 用途 |
|------|------|
| 8B `strategy_candidate_promotion` | Research → Candidate → REGISTERED |
| 8D `PromotionRunRecord` | 环境晋升 SSOT |

## 包结构

```text
backend_api_python/app/services/strategy_promotion/
  protocol.py              # ENGINE_VERSION=qd_strategy_promotion@1
  identity.py / policy.py / policy_presets.py
  fsm.py / lock.py / preconditions.py
  bridge_from_candidate.py / bridge_to_registry.py
  bridge_to_governance.py / bridge_to_runtime.py
  rollback.py / writers.py / artifact_store.py / runner.py
```

## API

`StrategyPromotionService(store, registry, *, strategy_registry, candidate_service, validation_service, governance)`：

- `submit_request(...)` → `PromotionRequest`
- `approve(request_id, operator, token)`
- `execute(request_id, inject=None)` → `PromotionRunRecord`（幂等）
- `rollback(strategy_code, to_version, reason, operator)` → `RollbackRecord`
- `get_run` / `list_runs` / `get_request`

## 存储

- D1：`workers/qd-research-d1/migrations/0034_strategy_promotion.sql`
  - `strategy_promotion_policy` / `strategy_promotion_request`
  - `strategy_promotion_run` / `strategy_promotion_rollback`
- R2：`qd/registry/promotions/{pipeline_run_id}/manifest.json`

## Non-goals

```text
❌ Auto LIVE
❌ Skip-level promotion (e.g. SHADOW→LIVE)
❌ Mutate strategy version during promotion
❌ Live performance monitoring (8E)
❌ Delete promotion history
❌ OMS submit
```
