# Phase 5 — Strategy Research

> **Status:** Phase 5A–5F implemented. Phase 6A–6D started — see [../phase6/README.md](../phase6/README.md).

## Roadmap

```text
Phase 5A  Strategy Definition / Contract   ← done
Phase 5B  Strategy Backtest               ← done
Phase 5C  Cost / Execution Model          ← done
Phase 5D  Qlib Strategy / Model Integration ← done
Phase 5E  QuantDinger ↔ Qlib Cross Validation ← done
Phase 5F  Research → Production Bridge    ← done
Phase 6A  Production Runtime / Online Data ← done (see phase6/)
Phase 6B  Portfolio & Position Service     ← done (see phase6/)
Phase 6C  Risk Engine                      ← done (see phase6/)
Phase 6D  OMS / Order Lifecycle            ← done (see phase6/)
Phase 6+  OMS / Broker
```

## Reading

1. [01_strategy_research.md](01_strategy_research.md)
2. [02_research_backtest.md](02_research_backtest.md)
3. [03_research_execution.md](03_research_execution.md)
4. [04_qlib_strategy_adapter.md](04_qlib_strategy_adapter.md)
5. [05_cross_validation.md](05_cross_validation.md)
6. [06_production_bridge.md](06_production_bridge.md)

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5a_strategy_research.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5b_research_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5c_research_execution.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5d_qlib_strategy.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5e_cross_validation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5f_production_bridge.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5a_strategy_research.py \
  tests/research_data/test_phase5b_research_backtest.py \
  tests/research_data/test_phase5c_research_execution.py \
  tests/research_data/test_phase5d_qlib_strategy.py \
  tests/research_data/test_phase5e_cross_validation.py \
  tests/research_data/test_phase5f_production_bridge.py -q \
  --confcutdir=tests/research_data
```

完整命令见 [COMMANDS_CN.md](../../COMMANDS_CN.md)。上游 Factor Lab：[phase4/README.md](../phase4/README.md)。
