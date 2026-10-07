# Phase 7D — Controlled Live Production

## 目标

在 `LIVE_CONTROLLED` 下**持续运行**（单账户 / 单策略 / 锁定研究版本 / 极小资金），强调生产可靠性：

```text
TradingSession (locked hashes)
  → LiveTradingRuntime.tick
  → MD → Strategy → Risk → OrderIntent
  → ControlledLiveGate + SafetyService.decide
  → Gateway → Broker (LIMIT, budgeted)
  → Continuous Recon + ShadowVsReal
  → Halt on breach (no auto scale)
```

## 边界（锁死）

**做**

- 扩展 `TradingSession`：`feature_version` / `processor_version` / `snapshot_id` / `stop_reason` / `RiskBudget`
- `LiveTradingRuntime` 粘合 `production_runtime`（仅 intents）与 `ControlledLiveService`
- Session/Daily 风险：越界 **STOP NEW ORDERS** + 告警；**不**自动 cancel/flatten
- Safety：`NORMAL → DEGRADED → HALTED → EMERGENCY`
- 持续 FAST 对账；CRITICAL → Session halt + `stop_reason=recon_mismatch`
- Operator Status + `controlled_live_*` metrics
- D1 `0029` + R2 `qd/production/controlled_live/.../runtime/...`

**7D 相对 7C 的终态策略**

- **FILLED 单笔不再默认 kill 全 session**（除非 `max_orders` 用尽或 UNKNOWN/REJECTED/risk/recon）

**不做（Non-goals）**

```text
❌ LIVE environment
❌ Multi-strategy / multi-account
❌ Auto capital increase
❌ Auto cancel/flatten
❌ Resubmit on timeout
❌ Secrets in git / D1 / audit plaintext
```

## 包

| 路径 | 职责 |
|------|------|
| `controlled_live/runtime.py` | LiveTradingRuntime tick 编排 |
| `controlled_live/risk_budget.py` | Session/Daily caps（env） |
| `controlled_live/stop_conditions.py` | pre/post tick HaltDecision |
| `controlled_live/reconcile_loop.py` | 持续 FAST recon |
| `controlled_live/operator_status.py` | OperatorStatusSnapshot |
| `controlled_live/metrics.py` | Ops counter helpers |

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7d_controlled_production.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7d_controlled_production.py -q \
  --confcutdir=tests/research_data
```

保持 7A/7B/7C 绿：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7c_controlled_live.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7c_controlled_live.py -q --confcutdir=tests/research_data
```
