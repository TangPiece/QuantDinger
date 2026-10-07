# Phase 8C — Strategy Validation Gate

## 目标

对 **已冻结** 的 `StrategyCandidate` 做**生产准入审查**（不重跑全量 Qlib 回测）：

```text
StrategyCandidate (8B VALIDATED)
  → ValidationRun (policy@version)
  → checks: Lineage / Leakage / PIT / CV / OOS / Overfit / Cost / Capacity / Risk / Stability
  → PASSED | FAILED | CONDITIONAL
  → Eligible for promote_to_registry（默认须 PASSED）
  ✕ Auto Shadow / LIVE / OMS
```

## 语义（锁死）

| 术语 | 含义 |
|------|------|
| 8B `VALIDATED` | 研究侧确认「可提交 Gate」 |
| 8C `ValidationRun.PASSED` | Gate 准入通过 |
| 8C `FAILED` | 准入拒绝（须新 Candidate） |
| `CONDITIONAL` | 软失败；**默认不可** `promote_to_registry` |

## 包结构

```text
backend_api_python/app/services/strategy_validation/
  protocol.py              # ENGINE_VERSION=qd_strategy_validation@1
  policy.py / policy_presets.py
  identity.py / pin.py
  bridge_from_candidate.py
  gates/                   # lineage, pit, cv, metrics, capacity, risk, stability
  report.py
  writers.py / artifact_store.py / runner.py
```

## API

`ValidationGateService(store, registry, *, candidate_service=None)`：

- `run(candidate_id, policy_id="default_research_v1", inject=None, operator="")`
- `get_run` / `list_runs`
- `get_policy` / `list_policies`

`StrategyCandidateService.promote_to_registry(..., require_gate_passed=True)`：最新 `ValidationRun.status` 须为 `PASSED`（8B 测试可 `require_gate_passed=False`）。

## 存储

- D1：`workers/qd-research-d1/migrations/0033_strategy_validation.sql`
  - `strategy_validation_policy`
  - `strategy_validation_run`
- R2：`qd/registry/validations/{validation_id}/result.json`

Candidate 仅可写 `metadata.last_validation_run_id` / `last_gate_status`（非 lineage）。

## Non-goals

```text
❌ Validation auto → Shadow/LIVE
❌ Mutate Candidate lineage
❌ Redefine 8B VALIDATED as Gate PASSED
❌ Full Qlib recompute inside Gate
❌ Delete validation history
```
