# Phase 5 — Strategy Research

> **Status:** Phase 5A implemented. 5B Research Backtest not started.

## Roadmap

```text
Phase 5A  Strategy Definition / Contract   ← done
Phase 5B  Strategy Backtest
Phase 5C  Cost / Execution Model
Phase 5D  Qlib Strategy / Model Integration
Phase 5E  QuantDinger ↔ Qlib Cross Validation
Phase 5F  Production Strategy
```

## Reading

1. [01_strategy_research.md](01_strategy_research.md)

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5a_strategy_research.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5a_strategy_research.py -q \
  --confcutdir=tests/research_data
```

完整命令见 [COMMANDS_CN.md](../../COMMANDS_CN.md)。上游 Factor Lab：[phase4/README.md](../phase4/README.md)。
