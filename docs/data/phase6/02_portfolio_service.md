# Phase 6B — Portfolio & Position Service

## Goal

Establish production **Account / Portfolio / Position** SSOT with available/frozen
quantities, event-sourced state, snapshots, PnL, and exposure. Consume
`TargetPosition` from Phase 6A and emit **PositionDelta** (PAPER may apply a
minimal fill). Stop before Risk Engine / OMS / Broker.

Engine version: `qd_portfolio_service@1`.

## Pipeline

```text
RuntimeTickResult.targets (6A / 5F TargetPosition)
  → PortfolioService.load Account+Portfolio
  → CurrentPosition / CashBalance
  → PositionDelta
  → [PAPER] PaperFillSimulator (instant fill @ as-of close)
  → PositionEvent → Reducer → State
  → PortfolioSnapshot / PnL / Exposure
  → STOP
```

## API

```python
PortfolioService(store, registry).open_account(
    *, environment="PAPER", market="CN_A", initial_cash=1_000_000
) -> Account

.bind_runtime(account_id, runtime_id, *, bundle_hash="") -> Portfolio

.apply_targets(
    account_id, targets, *,
    runtime_id="", run_id="", trading_date=None, prices=None, metadata=None
) -> ApplyTargetsResult
```

## Invariants

- `equity = available_cash + frozen_cash + market_value`
- `quantity = available_quantity + frozen_quantity`
- Idempotent: same apply key → `SKIPPED_IDEMPOTENT`

## Storage

- D1: `workers/qd-research-d1/migrations/0017_portfolio_service.sql`
- R2/local: `qd/production/portfolio/account={id}/year=/month=/day=/`

## Non-goals

```text
❌ LIVE / Broker / pending_orders
❌ Full Risk Engine (6C)
❌ OMS freeze lifecycle (6D) — FREEZE event type reserved
❌ Merge Strategy V2 LiveSession portfolio
❌ Sector / multi-currency / margin (P2)
❌ Mutate research backtest ledger as production SSOT
```

## Compatibility

- 6A / 5F unchanged; only **consumes** `targets`
- Does **not** emit production `OrderIntent` (6C: PositionDelta → Risk → OrderIntent)
- `ApplyTargetsResult` carries `account_id` / `portfolio_id` / `snapshot_id` / `deltas` for 6C
