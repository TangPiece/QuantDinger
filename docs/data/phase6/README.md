# Phase 6 — Production / Live Trading

> **Status:** Phase 6A–6J implemented.

## Roadmap

```text
Phase 6A  Production Runtime / Online Data   ← done
Phase 6B  Account / Position SSOT            ← done
Phase 6C  Risk Engine                        ← done
Phase 6D  OMS / Order Lifecycle              ← done
Phase 6E  Broker Adapter                     ← done (Paper + Fake + Alpaca Paper Reference)
Phase 6F  Reconciliation / Execution Reconciliation  ← done
Phase 6G  Trading Safety / Kill Switch               ← done
Phase 6H  Monitoring / Audit / Alert                 ← done
Phase 6I  Paper / Shadow E2E                         ← done
Phase 6J  Production Readiness                       ← done
```

## Reading

1. [01_production_runtime.md](01_production_runtime.md)
2. [02_portfolio_service.md](02_portfolio_service.md)
3. [03_risk_engine.md](03_risk_engine.md)
4. [04_oms.md](04_oms.md)
5. [05_broker_adapter.md](05_broker_adapter.md)
6. [06_reconciliation.md](06_reconciliation.md)
7. [07_safety.md](07_safety.md)
8. [08_ops_monitoring.md](08_ops_monitoring.md)
9. [09_paper_shadow_e2e.md](09_paper_shadow_e2e.md)
10. [10_production_readiness.md](10_production_readiness.md)

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
  python scripts/verify_phase6f_reconciliation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6g_safety.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6h_ops.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6i_e2e.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6j_readiness.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6f_reconciliation.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6g_safety.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6h_ops.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6i_e2e.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6j_readiness.py -q \
  --confcutdir=tests/research_data
```

## Notes

- **6A:** Bundle → Online Feature → 5F infer → OrderIntent（dry）
- **6B:** Account / Position / Event / Snapshot；SHADOW_DRY / PAPER_FILL
- **6C:** PositionDelta → RiskDecision → OrderIntent（无 OMS/Broker）
- **6D:** OrderIntent → Order 状态机 → Paper Broker → Fill → 6B PositionEvent
- **6E:** BrokerAdapter Contract；Paper + Fake REST/WS；Reference=Alpaca Paper；无 LIVE / Multi-Broker
- **6F:** BrokerSnapshot 对账；Finding/Gate；CRITICAL 上报 Safety；无自动补仓
- **6G:** Fail-Closed Safety Gate；Kill Switch；OMS submit 权威闸门；Emergency 仅 Contract
- **6H:** Health / Audit / Alert / Incident；trace_id；CRITICAL 告警 → Safety Policy（WARNING 不 HALT）
- **6I:** E2E-001…010；PAPER/SHADOW；Identity/Replay/ConsistencyScore；禁 LIVE
- **6J:** RDY-001…010；`recover_on_start`；`PRODUCTION_READY`；禁 LIVE / 真实资金
