# Phase 1D — Qlib Read Validation

> **Status:** Phase 1D implemented (Canonical → Materializer → pyqlib consistency).
> Phase 2 Qlib Adapter / Alpha158 / Model / Backtest remain out of scope.

## 1. Goal

Prove the closed loop is readable and semantically consistent:

```text
Canonical → DataQuery → Materializer → Qlib Cache → pyqlib(D.features) → PASS/FAIL
```

Not proving strategies — proving data infrastructure.

## 2. Six acceptance checks

| # | Check | How |
| --- | --- | --- |
| 1 | pyqlib reads Materializer cache | `qlib.init` + `D.features` non-empty (**hard gate**; filesystem fallback ≠ PASS) |
| 2 | DataQuery ↔ Qlib OHLCV panel | instrument / date / open/high/low/close/volume/amount |
| 3 | PIT leakage | `available_time <= knowledge_time`; Materializer never calls `fundamental` |
| 4 | Universe survivor bias | historical `valid_from/valid_to` × DQ.universe(T) × Qlib instruments |
| 5 | Price policy | `none`(raw) / `post`(qfq) via `D.features`; Canonical raw unchanged; `pre` still N/I |
| 6 | Dataset hash | rematerialize → same hash/checksum; change `price_policy` → new hash |

## 3. Architecture

```text
                    Canonical R2 / Local
                         │
                         ▼
                    DataQuery
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        QuantDinger Frame       Materializer
                                      │
                                      ▼
                                 Qlib Cache
                                      │
                                      ▼
                                  pyqlib
                                      │
                                      ▼
                              Consistency Suite
```

Code:

- Materializer: `backend_api_python/app/services/research_data/qlib_materializer/`
- PIT-safe panel helper: `backend_api_python/app/services/research_data/phase1d_panel.py`
- Tests: `tests/research_data/test_phase1d_*.py`
- CLI: `scripts/verify_phase1d_consistency.py`

## 4. Universe as_of (locked)

`DefaultQlibMaterializer` **must not** use `datetime.now()` for universe membership.

- Prefer explicit `end=` constructor window
- Else derive as_of from `max(trading_date)` after a provisional member-union market probe
- Fixture includes survivor rows: `CNStock:999999` (exited 2023-12-31), `CNStock:688001` (joined 2024-04-01)

## 5. PIT policy (locked)

- Default Qlib Cache remains **market OHLCV only** (no ROE bins)
- PIT gate stays on `DataQuery.fundamental(knowledge_time)`
- `build_pit_safe_research_panel` joins market ∪ PIT-filtered fundamentals for Phase 2 Adapter input contract
- Materializer must never call `fundamental`

Narrative fixture: synthetic ROE `available_time=2024-04-30` → invisible at `2024-04-29`, visible at `2024-05-01`.

## 6. Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase1d_consistency.py

QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python -m pytest tests/research_data/test_phase1d_*.py -q
```

Exit codes: `0` PASS, `1` FAIL, `2` pyqlib missing.

## 7. Explicit non-goals

```text
❌ Alpha158 / LightGBM / Transformer
❌ Factor Mining / Signal / Strategy / Backtest / RL / RD-Agent
❌ QuantDingerQLibHandler (Phase 2)
❌ pre / hfq adjustment implementation
```

## 8. Next

After Phase 1D PASS → Phase 2 Qlib Adapter (Dataset / Handler / Processor), still without claiming production PnL parity.
