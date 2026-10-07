# Production Checklist

Machine gate: `verify_phase6j_readiness.py` sets `PRODUCTION_READY=true` when all RDY-001…010 pass.

| Check | Scenario |
|-------|----------|
| Crash Recovery | RDY-001 |
| Idempotency | RDY-002 |
| Execution Dedup | RDY-003 |
| UNKNOWN Recover | RDY-004 |
| Out-of-Order | RDY-005 |
| Broker Reconnect | RDY-006 |
| Registry Persistence | RDY-007 |
| Kill Switch | RDY-008 |
| Operator Override | RDY-009 |
| Replay + PIT | RDY-010 |

Non-goals: Live trading, auto-enable Live, 24h soak as merge gate.
