# Phase 7E — Gradual Scale (Trading Governance)

## 目标

建立 **Live Trading Governance Layer**：策略生命周期、资金/风险预算分层、Scale Level 人工审批放量、多策略聚合与持仓归因、多账户绑定。最高档 **L4** 且经 **LIVE_ENV_APPROVAL** 后才可进入 `LIVE` 环境 ladder。

## 边界（锁死）

**做**

- `app/services/trading_governance/`（`ENGINE_VERSION=qd_governance@1`）
- D1 `0030_trading_governance.sql` + R2 `qd/production/governance/...`
- Controlled Live 消费 `EffectiveCaps` 快照（session `scale_level` + metadata）
- OMS/Gateway/Modes：`LIVE` 默认仍拒；须 governance 授权

**不做（Non-goals）**

- ❌ 仅按 PnL 自动升档
- ❌ LIVE 策略版本原地 mutate
- ❌ 自动 cancel/flatten
- ❌ 无限策略/账户

## Scale Level

| Level | 典型 env |
|-------|----------|
| L0_SHADOW | SHADOW |
| L1–L3 | LIVE_CONTROLLED |
| L4_PRODUCTION | LIVE（需 L4 + PRODUCTION_READY + LIVE_ENV_APPROVAL + 审批） |

升档：`request_scale_up` → criteria report → **人工** `approve_scale` → `apply_scale`。

## 验收

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7e_gradual_scale.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7e_gradual_scale.py -q \
  --confcutdir=tests/research_data
```

LIVE 环境变量（仅运维显式开启，CI 默认关闭）：

```bash
export PRODUCTION_READY=true
export LIVE_ENV_APPROVAL=true
```
