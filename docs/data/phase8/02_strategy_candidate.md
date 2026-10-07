# Phase 8B — Research → Strategy Candidate

## 目标

从 **Experiment / Backtest / Evaluation** 冻结 Research Lineage，生成可治理的 **StrategyCandidate**（≠ Live 策略，≠ `production_bundle.status=CANDIDATE`）。

```text
Experiment → Backtest → Evaluation
  → StrategyCandidate (frozen lineage)
  → READY_FOR_VALIDATION / VALIDATED
  → (optional) register into Strategy Registry 8A
  ✕ Shadow / LIVE（→ 8C/8D）
```

- `VALIDATED`（8B）= 研究侧评估包已冻结并人工/脚本确认「可提交 Gate」，**不是** 8C Validation Gate PASSED
- `promote_to_registry` 仅 `VALIDATED` → 8A `register_version_manual` + `PromotionRecord`（8C 起默认还须最新 `ValidationRun.status=PASSED`，测试可 `require_gate_passed=False`）

## 包结构

```text
backend_api_python/app/services/strategy_candidate/
  protocol.py              # ENGINE_VERSION=qd_strategy_candidate@1
  identity.py / pin.py / state_machine.py
  bridge_from_research.py / promotion.py
  writers.py / artifact_store.py / runner.py
```

## 状态机

```text
DRAFT → GENERATED → EVALUATING → READY_FOR_VALIDATION → VALIDATED
EVALUATING → REJECTED
READY_FOR_VALIDATION | VALIDATED → EXPIRED
禁：任意 → SHADOW/LIVE；禁跳过 GENERATED 直接 VALIDATED
```

`generate()` 时冻结 lineage；`VALIDATED` 后核心 pin 不可变，修改须新 Candidate。

## 存储

- D1：`workers/qd-research-d1/migrations/0032_strategy_candidate.sql`
  - `strategy_candidate`
  - `strategy_candidate_promotion`
- R2：`qd/registry/candidates/{candidate_id}/manifest.json`

## API（门面）

`StrategyCandidateService`：

- `create_from_research` / `generate` / `start_evaluating` / `mark_ready` / `mark_validated`
- `reject` / `expire`
- `promote_to_registry`（仅 VALIDATED → 8A）
- `get` / `list` / `get_promotions`

## Non-goals

```text
❌ Backtest → Live
❌ Auto Shadow / LIVE
❌ Validation Gate (8C)
❌ Delete historical candidates
❌ Confuse production_bundle CANDIDATE with StrategyCandidate
```
