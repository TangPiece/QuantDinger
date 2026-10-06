# Phase 6 — Production / Live Trading

> **Status:** Phase 6A implemented. 6B+ not started.

## Roadmap

```text
Phase 6A  Production Runtime / Online Data   ← done
Phase 6B  Account / Position SSOT
Phase 6C  Risk Engine
Phase 6D  OMS / Order Lifecycle
Phase 6E  Broker Adapter / LIVE
Phase 6F  Reconciliation / P&L
```

## Reading

1. [01_production_runtime.md](01_production_runtime.md)

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6a_production_runtime.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6a_production_runtime.py -q \
  --confcutdir=tests/research_data
```

## Boundary (6A)

- Loads **DEPLOYED** ProductionBundle (Phase 5F)
- PAPER / SHADOW only → **OrderIntent**
- No Broker / OMS / LIVE / pending_orders
