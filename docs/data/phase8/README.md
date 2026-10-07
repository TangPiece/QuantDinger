# Phase 8 — Research → Production Strategy Lifecycle

> **Status:** Phase 8A–8B implemented (Registry + Strategy Candidate).

## Roadmap

```text
8A  Strategy Registry          ← done
8B  Research → StrategyCandidate ← done
8C  Validation Gate
8D  Promotion Pipeline + PromotionRecord
8E  Live Performance Feedback / Drift
8F  Strategy Health Monitoring
8G  Automatic demote (upgrade still human-approved)
8H  Retirement (history never deleted)
```

## Reading

1. [01_strategy_registry.md](01_strategy_registry.md)
2. [02_strategy_candidate.md](02_strategy_candidate.md)

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8a_strategy_registry.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8a_strategy_registry.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8b_strategy_candidate.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8b_strategy_candidate.py -q \
  --confcutdir=tests/research_data
```

Phase 7E verify 仍应绿（8A 不自动 LIVE / 不改 OMS 默认）：

```bash
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7e_gradual_scale.py
```
