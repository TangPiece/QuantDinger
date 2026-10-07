# Phase 8 — Research → Production Strategy Lifecycle

> **Status:** Phase 8A–8I implemented (Registry + Candidate + Validation Gate + Promotion + Performance Feedback + Monitoring + Guardrails + Production→Research Feedback + Architecture Hardening E2E).

## Roadmap

```text
8A  Strategy Registry          ← done
8B  Research → StrategyCandidate ← done
8C  Validation Gate            ← done
8D  Promotion Pipeline         ← done
8E  Live Performance Feedback / Drift ← done
8F  Strategy Health Monitoring  ← done
8G  Strategy Governance & Auto Guardrails  ← done
8H  Production → Research Feedback Loop  ← done
8I  Architecture Hardening & E2E Acceptance  ← done
```

## Reading

1. [01_strategy_registry.md](01_strategy_registry.md)
2. [02_strategy_candidate.md](02_strategy_candidate.md)
3. [03_validation_gate.md](03_validation_gate.md)
4. [04_promotion_pipeline.md](04_promotion_pipeline.md)
5. [05_live_performance_feedback.md](05_live_performance_feedback.md)
6. [06_strategy_monitoring.md](06_strategy_monitoring.md)
7. [07_strategy_governance_guardrails.md](07_strategy_governance_guardrails.md)
8. [08_production_research_feedback.md](08_production_research_feedback.md)
9. [09_architecture_hardening_e2e.md](09_architecture_hardening_e2e.md)

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

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8c_validation_gate.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8c_validation_gate.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8d_promotion_pipeline.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8d_promotion_pipeline.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8e_performance_feedback.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8e_performance_feedback.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8f_strategy_monitoring.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8f_strategy_monitoring.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8g_strategy_guardrails.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8g_strategy_guardrails.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8h_production_research_feedback.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8h_production_research_feedback.py -q \
  --confcutdir=tests/research_data

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8i_architecture_hardening.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8i_architecture_hardening.py -q \
  --confcutdir=tests/research_data
```

Phase 7E verify 仍应绿（8A 不自动 LIVE / 不改 OMS 默认）：

```bash
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7e_gradual_scale.py
```
