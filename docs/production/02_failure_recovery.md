# Failure Recovery

On process start, call `OMSService.recover_on_start()`: scan `SUBMITTED`/`UNKNOWN` and PENDING outbox, **query broker only**, apply `ExecutionReport`, never re-submit filled orders. `RecoverReport.resubmit_attempted` is always `False`.
