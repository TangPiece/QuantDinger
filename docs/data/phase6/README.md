# Phase 6 — Production / Live Trading

> **Status:** Phase 6A–6E implemented. 6F+ not started.

## Roadmap

```text
Phase 6A  Production Runtime / Online Data   ← done
Phase 6B  Account / Position SSOT            ← done
Phase 6C  Risk Engine                        ← done
Phase 6D  OMS / Order Lifecycle              ← done
Phase 6E  Broker Adapter                     ← done (Paper + Fake + Alpaca Paper Reference)
Phase 6F  Reconciliation / P&L
```

## Reading

1. [01_production_runtime.md](01_production_runtime.md)
2. [02_portfolio_service.md](02_portfolio_service.md)
3. [03_risk_engine.md](03_risk_engine.md)
4. [04_oms.md](04_oms.md)
5. [05_broker_adapter.md](05_broker_adapter.md)

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6a_production_runtime.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6b_portfolio_service.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6c_risk_engine.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6d_oms.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6e_broker_adapter.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6e_broker_adapter.py -q \
  --confcutdir=tests/research_data
```

## Notes

- **6A:** Bundle → Online Feature → 5F infer → OrderIntent（dry）
- **6B:** Account / Position / Event / Snapshot；SHADOW_DRY / PAPER_FILL
- **6C:** PositionDelta → RiskDecision → OrderIntent（无 OMS/Broker）
- **6D:** OrderIntent → Order 状态机 → Paper Broker → Fill → 6B PositionEvent
- **6E:** BrokerAdapter Contract；Paper + Fake REST/WS；Reference=Alpaca Paper；无 LIVE / Multi-Broker
