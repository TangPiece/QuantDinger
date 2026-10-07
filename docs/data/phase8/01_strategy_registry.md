# Phase 8A — Strategy Registry

## 目标

统一 **Strategy Registry**，回答「这个实盘策略到底钉住哪个 Model / Dataset / Feature / Policy？」——作为 Phase 8 的身份层 SSOT。

```text
Strategy (strategy_code)
  └── StrategyVersion
        ├── dataset_hash / snapshot_id
        ├── model_version / model_artifact_id
        ├── feature_version / processor_version
        ├── strategy_hash / bundle_hash
        ├── risk_policy_ref
        └── execution_policy_ref
```

- `strategy_id` ≡ 规范化 `strategy_code`（与 5A `research_strategy` 对齐）
- 版本注册后 **immutable**；改 pin 须新 `strategy_version` label
- 从 **APPROVED/DEPLOYED** `ProductionBundle` 注册（`bridge_from_production`）
- 薄写入 7E `gov_strategy_version` / `active_version`（`link_governance_active`）
- **无** auto promote → LIVE、**无** Validation Gate、**无** OMS submit

## 包结构

```text
backend_api_python/app/services/strategy_registry/
  protocol.py                 # ENGINE_VERSION=qd_strategy_registry@1
  identity.py / pin.py / bindings.py
  bridge_from_production.py / bridge_to_governance.py
  resolver.py / writers.py / artifact_store.py / runner.py
```

`content_hash` 算法 SSOT 在 `strategy_registry.pin`；7E `trading_governance.strategy_registry` 委托同一函数。

## 存储

- D1：`workers/qd-research-d1/migrations/0031_strategy_registry.sql`
  - `strategy_registry`（`strategy_code` PK）
  - `strategy_version_binding`（`version_id` PK；唯一 `(strategy_code, strategy_version)`）
- R2：`qd/registry/strategies/{strategy_code}/versions/{version_id}/manifest.json`

## API（门面）

`StrategyRegistryService`：

- `register_strategy` / `register_version_from_bundle` / `register_version_manual`
- `set_policy_bindings`（已注册版本拒改）
- `get_version` / `get_active` / `list_versions` / `resolve`
- `link_governance_active`（写 7E active_version，不 promote LIVE）

## Phase 8 后续（占位，本阶段不实现）

```text
8B  Research → StrategyCandidate  ← see 02_strategy_candidate.md
8C  Validation Gate
8D  Promotion Pipeline + PromotionRecord
8E  Live Performance Feedback / Drift
8F  Strategy Health Monitoring
8G  Automatic demote
8H  Retirement
```

## Non-goals

```text
❌ Auto promote RESEARCH → LIVE
❌ Validation Gate / Candidate (8B/8C)
❌ Delete historical versions
❌ Merge legacy strategy_lifecycle.py robots
❌ Secrets in git / D1 / audit plaintext
```
