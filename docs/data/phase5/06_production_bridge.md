# Phase 5F — Research → Production Bridge

> **Status:** Implemented. Freeze validated research into immutable Production Bundles.
> Stops at research `OrderIntent`. **Not** Broker / OMS / Live trading (Phase 6).

## Boundary

```text
5A strategy_hash + 5E cv_hash (PASSED*)
  → freeze ProductionBundle (bundle_hash)
  → DRAFT → VALIDATED → CANDIDATE → APPROVED → DEPLOYED
  → dry-run Inference → Signal → TargetPosition → OrderIntent
  → STOP
```

Package: `app/services/research_data/production_bridge/`  
Engine: `qd_production_bridge@1`  
`bundle_hash` here is the **production** identity — do not confuse with 2A `ResearchBundleIdentity.bundle_hash`.

## Principles

1. Production does **not** re-interpret research — only Load → Validate → Infer → OrderIntent.
2. **DRAFT cannot deploy.** **APPROVED is immutable** (changes require a new hash).
3. Reuse 5A `Signal` / `TargetPosition` / research `OrderIntent`.
4. No `import qlib` / `ProductionBacktestEngine` / Broker in this package.

## State machine

```text
DRAFT → VALIDATED → CANDIDATE → APPROVED → DEPLOYED ⇄ PAUSED → RETIRED
```

| Action | Rule |
| --- | --- |
| freeze | → DRAFT |
| validate | integrity + data quality + feature parity |
| promote | CV status ∈ {PASSED, PASSED_WITH_EXPECTED_DIFF} |
| approve | immutable thereafter |
| deploy | only APPROVED/PAUSED; one DEPLOYED per strategy_code |
| rollback | switch deployment pointer to prior bundle_hash |

## Storage

```text
qd/production/bundles/{bundle_hash}/
  manifest.json
  summary.json
  strategy/snapshot.json
  config/execution_policy.json
  dependency/lock.json
  processor/  model/  feature/parity_report.json
  checksums.json

qd/production/runs/{run_id}/
  inference.json
```

D1: `0015_production_bridge.sql` — `production_bundle`, `production_deployment`, `production_deployment_run`.

## API

```python
from app.services.research_data.production_bridge import (
    ProductionBridgeService,
    InferenceRequest,
)

svc = ProductionBridgeService(store, registry)
r = svc.freeze(strategy_hash, metadata={...})
svc.validate(r.bundle_hash, metadata={...})
svc.promote(r.bundle_hash)
svc.approve(r.bundle_hash)
svc.deploy(r.bundle_hash)

resp = svc.infer(
    InferenceRequest(bundle_hash=r.bundle_hash, trading_date=...),
    metadata={"factor_rows": [...], "price_bars": [...]},
)
# resp.order_intents — dry-run only
```

## Gates

- **DataQualityGate (P0):** completeness, bad prices, future timestamps, NaN/Inf, universe, identity.
- **SignalGate (P0):** max single weight, max gross, turnover, universe, stale signal.
- P0 failure → `InferenceResponse.status=STOPPED` (no intents).

## Feature parity

Offline and Online evaluators share the same evaluation function over `FeatureDefinition` / factor score rows. Mismatch → validate FAIL.

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5f_production_bridge.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5f_production_bridge.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Broker / OMS / Account / Fill / Live orders
❌ ProductionBacktestEngine as live runner
❌ Second Signal/OrderIntent contract (live_trading)
❌ Merge Strategy V2 deployment
❌ Canary / auto-rollback / drift (P2)
❌ Rewrite Qlib or 5A Contract
```

## Phase 6 handoff

DEPLOYED `bundle_hash` + research `OrderIntent` are the only inputs for the Production Trading Platform.
