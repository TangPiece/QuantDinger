# Phase 3E — Dual Engine Consistency

> **Status:** implemented. Compares Qlib Research vs QuantDinger Production on the same Canonical Signal; differences must be **fully attributable**.

## Goal

```text
                 same Dataset / Snapshot / Signal
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
           Qlib Research     QD Production
                 │                 │
                 └────────┬────────┘
                          ▼
                 ConsistencyEngine
                          ▼
              ConsistencyReport + Attribution
```

**Not** “returns must always match”.  
**Yes** — every material difference must map to a known component (commission / slippage / T+1 / lot / limit / suspend / cash). **Unknown Difference → FAILED.**

## Package

```text
backend_api_python/app/services/research_data/backtest_consistency/
```

| Module | Role |
| --- | --- |
| `levels.py` | L0–L5 policy ladder |
| `diff.py` | equity / position / trade / cost / cash / rejected |
| `attribution.py` | Production ladder incremental return impact |
| `runner.py` | `ConsistencyEngine.run` |
| `artifact_store.py` | `qd/artifacts/consistency/{run_id}/` |
| `signal_check.py` | Canonical Signal artifact sanity |

Domain extras:

- `compute_semantic_fingerprint` — same as request fingerprint **without** `engine`
- `ConsistencyRunRecord` in Registry (Local JSON; D1 via artifact metadata)

## Levels

| Level | Policy delta | Expectation |
| --- | --- | --- |
| L0 Ideal | T+0 close, zero cost, lot=1, no limits | Dual-engine equity/cash/position ≤ 1e-6 when both run |
| L1 | + commission | Cost gap explained |
| L2 | + slippage | Fill / equity impact explained |
| L3 | T+1 open | Return gap attributable to delay |
| L4 | lot_size=100 floor | Quantity gap → `LOT_SIZE_*` |
| L5 | limit / suspend / cash / stamp | QD ≠ Qlib allowed; **no Unknown** |

Attribution uses **Production re-runs** L0→L5 on the same Signal/Bars; Qlib is the research anchor when available.

## Artifact

```text
qd/artifacts/consistency/{run_id}/
  manifest.json
  summary.json
  equity_diff.parquet
  position_diff.parquet
  trade_diff.parquet
  cost_diff.parquet
  attribution.parquet
```

Registry: `consistency_run` → `run_id`, `dataset_hash`, result ids, status, max diffs, `artifact_uri`.

## Golden Dataset

```text
backend_api_python/tests/research_data/consistency/
  scenarios.yaml
  golden/market/bars.csv
  golden/signals/targets.csv
  golden/expected/{L0..L5}/equity|trades|positions.parquet
```

~5 instruments × ~20 trading days; synthetic limit / suspend / lot / T+1 / costs. No 10-year live tape in CI.

## Verify

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3e_consistency.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3e_*.py -q \
  --confcutdir=tests/research_data
```

Without pyqlib: Production ladder + report still run (`SKIPPED_QLIB`). Dual-engine L0 hard assert uses `pytest.importorskip("qlib")` / verify notes `qlib: missing`.

## Non-goals

```text
❌ Phase 4 Factor Lab
❌ Require Qlib Return == Production Return on L3+
❌ 10y live market as CI Golden
❌ Rewrite Qlib matching / qlib types in Domain
```
