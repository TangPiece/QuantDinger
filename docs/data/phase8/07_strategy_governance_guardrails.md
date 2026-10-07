# Phase 8G — Strategy Governance & Auto Guardrails

## 目标

> Monitoring 发现 → Guardrail 保护 → Governance 决策。

```text
8F Health / Alert / GovernanceReviewEvent
  → Guardrail Evaluation (GuardrailPolicy + Action Matrix)
  → AUTO (WARN / THROTTLE / PAUSE | Safety STOP NEW ORDERS)
    or REVIEW (GovernanceIncident → GovernanceDecision)
  → StrategyRuntimeState + GovernanceEvent + audit
  ✕ mutate StrategyVersion / Dataset / Model
  ✕ auto PROMOTE / RETIRE / capital reallocation
  ✕ flatten / cancel_all by default
```

## 双状态（硬约束）

- **Lifecycle**（8D/7E）：`SHADOW` / `CONTROLLED_LIVE` / `LIVE` / `RETIRED` — 8G 只读镜像字段 `lifecycle_phase`
- **Runtime**（8G）：`ACTIVE` / `DEGRADED` / `THROTTLED` / `PAUSED` / `STOPPED` / `ROLLBACK_PENDING` / …

`LIVE` + `THROTTLED` 合法；恢复 Runtime ≠ 改 Lifecycle。

## AutoActionPolicy（默认）

允许自动（`GuardrailPolicy.auto_execute=true`）：`WARN`, `THROTTLE`, `PAUSE`

默认禁止自动：`STOP`, `ROLLBACK`, `PROMOTE`, `RETIRE`, `DEMOTE`

Safety 例外：`EMERGENCY` + (`RISK`|`RECONCILIATION`|`MARKET_DATA`) → Safety Stop NEW ORDERS（6G/7E kill，无 flatten）

Performance / Signal / Capacity CRITICAL → `GovernanceIncident` `REVIEW_REQUIRED`，不自动 STOP/ROLLBACK

## 包结构

```text
strategy_guardrails/
  protocol.py              # ENGINE_VERSION=qd_strategy_guardrails@1
  policy.py / policy_presets.py / action_matrix.py / auto_action_policy.py
  fsm.py / runtime_state.py / incident.py / decision.py
  evaluators/              # from_monitoring, inject
  actions/                 # warn, throttle, pause, safety_stop, resume, rollback
  bridges/                 # monitoring, trading_governance, safety, promotion
  capital_guard.py / writers.py / artifact_store.py / runner.py
```

## Service API

`StrategyGuardrailsService(store, registry, *, monitoring=None, governance=None, safety=None, promotion=None)`：

- `evaluate_from_monitoring(strategy_code, *, inject=None)`
- `get_runtime_state` / `list_incidents` / `get_incident`
- `submit_decision` / `execute_approved_decision`
- `resume` / `rollback` / `list_events`

**无** `promote` / `retire` / `reallocate_capital` / `mutate_version`

8F 薄钩：`collect_and_evaluate` 成功后可选 `evaluate_from_monitoring`（吞异常）。

## 存储

- D1：`workers/qd-research-d1/migrations/0037_strategy_guardrails.sql`
- R2：`qd/registry/strategy_guardrails/{strategy_code}/runtime|incidents|decisions|events|rollbacks/...`

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8g_strategy_guardrails.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase8g_strategy_guardrails.py -q --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Auto promote / retire / capital reallocation
❌ Mutate Immutable StrategyVersion
❌ Flatten / cancel_all as default guardrail
❌ Replace 8F / 6G / 7E scale-up approval
❌ Research feedback loop（→ 8H）
```
