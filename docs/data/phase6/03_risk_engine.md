# Phase 6C — Risk Engine

## Goal

Independent, versioned, composable risk decisions over **PositionDelta** /
account state. Output research **OrderIntent** only. No OMS / Broker.

Engine version: `qd_risk_engine@1`.

## Pipeline

```text
ApplyTargetsResult (6B, prefer SHADOW_DRY)
  → RiskContext + RiskPolicy@version
  → RiskRules (P0)
  → RiskDecision (ALLOW|ALLOW_REDUCE|MODIFY|REJECT|ERROR)
  → adjusted PositionDelta (clip-only, never increase strategy risk)
  → OrderIntent
  → RiskSnapshot + RiskDecisionEvent
  → STOP
```

## API

```python
RiskEngineService(store, registry).register_policy(policy) -> RiskPolicy

.evaluate(
    apply_result=None, *,
    deltas=None, account=None, positions=None,
    policy=None, policy_ref=None,
    trading_status=None, prices=None, signals=None, metadata=None,
) -> RiskEvaluateResult
```

## P0 Rules

- `ACCOUNT_STATE` — ACTIVE; cash; available qty; no short (default)
- `UNIVERSE`
- `TRADING_STATUS` — suspended / limit-up buy / limit-down sell
- `DATA_FRESHNESS` / `SIGNAL_FRESHNESS`
- `MAX_SINGLE_POSITION` / `MAX_POSITION_DELTA` / `MAX_TURNOVER` / `MAX_GROSS_EXPOSURE`

## Principles

- Risk may **reduce** targets only; never raise them.
- Production OrderIntent authority is 6C (5F/6A dry-run unchanged).
- Prefer 6B `SHADOW_DRY` upstream of Risk → OMS (6D).

## Storage

- D1: `workers/qd-research-d1/migrations/0018_risk_engine.sql`
- R2/local: `qd/production/risk/{risk_run_id}/`

## Non-goals

```text
❌ OMS / pending_orders / Broker order id
❌ LIVE trading
❌ TWAP/VWAP/POV
❌ ML risk / full kill-switch
❌ Merge Strategy V2 or live_trading.account_risk
❌ Increase strategy target risk
```

## Compatibility

- 6A/6B/5F unchanged
- Optional [`SixCRiskGatePort`](../../../backend_api_python/app/services/risk_engine/gate_adapter.py) implements 6A `RiskGatePort`
- Downstream 6D：[`OMSService.submit_intents`](../../../backend_api_python/app/services/oms/runner.py) 消费 `order_intents` + `risk_run_id` / `policy_hash`
