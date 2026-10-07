# Phase 8I — Architecture Hardening & End-to-End Acceptance

## 目标

**不是**新业务能力，而是证明 8A～8H 组成可运行的 Strategy Lifecycle：

- Research / Trading **平面隔离**（静态 AST 扫描）
- **FSM** 非法跳转被拒；**Runtime PAUSED ≠ Lifecycle RETIRED**
- Registry / Candidate / Baseline / Snapshot / Rollback **不可偷改**
- **Failure Injection 矩阵**（compose 8C～8H Fake inject）
- 一条 **E2E golden 链**：Candidate → Validation → SHADOW → Feedback → Monitor → Guardrail → FailureCase → Hypothesis → Experiment → `DataQuery.production_feedback`

```text
8A–8H verify scripts (still green)
  + scan_phase8_plane_isolation
  + phase8_hardening/* helpers (tests only)
  + phase8_lifecycle_golden E2E chain
  ✕ 新 Domain ENGINE_VERSION / D1 0039 / Flask / LIVE OMS E2E
```

## 交付物

| 路径 | 说明 |
|------|------|
| `scripts/scan_phase8_plane_isolation.py` | AST + source 扫描 8 个 lifecycle 包 |
| `scripts/verify_phase8i_architecture_hardening.py` | 编排 8A–8H + 8I 检查 + 7E 回归 |
| `tests/research_data/phase8_hardening/` | FSM / immutability / inject / lineage helpers |
| `tests/research_data/phase8_lifecycle_golden/` | 单 tmp 环境 E2E 链 |
| `tests/research_data/test_phase8i_architecture_hardening.py` | pytest 覆盖 |

## Failure Injection 矩阵（Fake）

| 场景 | 来源 |
|------|------|
| Market Data CRITICAL | 8F `golden_market_data_critical_inject` |
| Recon EMERGENCY → Safety Stop | 8G recon inject |
| Risk CRITICAL → PAUSE | 8G risk inject |
| Slippage → THROTTLE | 8G slippage inject |
| Perf CRITICAL → REVIEW_REQUIRED（不自动 STOP） | 8G performance inject |
| Bad PIT lineage → QualityGate REJECT | 8H bad PIT inject |
| Drift CRITICAL | 8E drift inject |
| SHADOW→LIVE 拒 | 8D promotion FSM |

## E2E 链（锁死）

```text
seed registry/candidate (8A/8B)
→ validation PASS (8C)
→ promote SHADOW COMPLETED (8D)
→ freeze baseline + drift comparison (8E)
→ monitor CRITICAL (8F)
→ guardrail PAUSE (8G)
→ dataset + snapshot + failure_case + hypothesis + link_experiment (8H)
→ DataQuery.production_feedback 可读
→ assert lineage parent_* + runtime≠lifecycle + immutables
```

## 验收

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8i_architecture_hardening.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8i_architecture_hardening.py -q \
  --confcutdir=tests/research_data
```

`verify_phase8i` 输出 JSON 含 `checks`：

- `phase8a_to_8h_verifies`
- `plane_isolation_scan`
- `fsm_illegal_transitions_rejected`
- `runtime_lifecycle_separation`
- `immutability_battery`
- `lineage_forward_and_back`
- `failure_inject_matrix`
- `e2e_lifecycle_chain`
- `phase7e_regression`

## Non-goals

```text
❌ New strategy domain features
❌ Live broker chaos engineering
❌ Phase 9 factor/model platform
❌ D1 0039 / 新 ENGINE_VERSION Domain
```
