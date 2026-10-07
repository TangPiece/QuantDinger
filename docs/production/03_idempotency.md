# Idempotency

Order submit uses idempotency keys; duplicate intents return the same order. Execution dedup uses broker execution identity. Verify with RDY-002 and RDY-003.
