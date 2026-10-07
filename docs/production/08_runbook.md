# Runbook

## Broker disconnect

1. Confirm Ops health `DEGRADED`.
2. Do **not** re-submit open orders; call `recover_on_start`.
3. Reconnect adapter / pump WS with dedup.
4. Run FAST reconciliation; if CRITICAL, Safety blocks until operator ack.

## Crash after submit

1. Restart process → `recover_on_start`.
2. Verify `resubmit_attempted == false` and broker order count unchanged.
3. Reconcile positions.

## Kill Switch engaged

1. Acknowledge incident (`SAFETY_ACKNOWLEDGE` audit).
2. Resolve root cause.
3. `resume` with operator actor (`SAFETY_RESUME` audit).

See `scripts/soak_paper_stub.py` for 24h Paper soak steps (manual, non-gate).
