# 07 — Qlib Research Backtest (Phase 3B)

> **Status:** Implemented.
> Default policy: `research_qlib_relaxed()` (T+0, close fill).
> Full A-share T+1 / lot / limit matching is **not** guaranteed here (Phase 3C/3D).

## Pipeline

```text
BacktestRequest (engine=qlib)
  → load TargetPosition artifact
  → QlibResearchBacktestEngine.run
  → qlib.backtest.backtest
  → BacktestResult (Domain)
```

Package: `backend_api_python/app/services/research_data/backtest_qlib/`  
(Domain contract stays in `backtest/` with **no** `import qlib`.)

## Engine steps

1. Reject non-`qlib` engine.
2. Load Experiment; require `dataset_hash` match.
3. Require `target_positions_artifact_id`; load `target_positions.parquet`.
4. `QlibAdapter.ensure_cache(dataset_ref)` → `QlibRuntime.activate`.
5. Build `QuantDingerWeightStrategy` + Exchange kwargs + daily `SimulatorExecutor`.
6. Call `qlib.backtest.backtest(...)`.
7. Map PORT/INDICATOR metrics → `BacktestResult`.
8. Persist under `qd/artifacts/backtest/{result_id}/`; optional MLflow tags.

## Weight strategy semantics

| Case | Behavior |
| --- | --- |
| Day present in TargetPosition | Rebalance toward that day's weights |
| Day missing | **No rebalance** (hold previous) |
| All weights ≈ 0 | Clear tradable positions |
| TopK | Not re-implemented; already decided in Signal (2E) |

Instrument keys `CNStock:xxx` → `to_qlib_instrument` → lowercase Qlib ids.

## Policy mapping (simplified)

| Domain | Qlib Exchange |
| --- | --- |
| `execution_price` / `reference_price` | `deal_price` |
| commission + stamp (+ slip bps) | `open_cost` / `close_cost` |
| `minimum_commission` | `min_cost` |
| `lot_size` (if >1 and not fractional) | `trade_unit` |
| `limit_up_down` + pct | `limit_threshold` or `None` |

`cn_equity_close_signal_next_open` may be attached to a Request, but **behavior may diverge** from a true A-share exchange. Strict compliance is Phase 3C/3D.

## Request extension

- Optional `dataset_ref` on `BacktestRequest` (also filled by `from_experiment`).
- Included in `compute_request_fingerprint` when set.
- Verify / minimal runs: `benchmark=None` if golden has no index (skip bench metrics).

## Artifacts

```text
qd/artifacts/backtest/{result_id}/
  result.json
  equity.parquet      # optional
  trades.parquet      # optional
  qlib_report.parquet # optional raw report
```

`engine_version`: `qlib_research_backtest@1`

## Non-goals

```text
❌ Production Backtest
❌ Full T+1 / 100-share lot enforcement / real suspension matching
❌ Tick / Level2 / Nested Backtest / RL
❌ Rewrite TopK (lives in Signal layer)
❌ Modify strategy_v2 / Agent backtest
❌ import qlib inside research_data/backtest/
```

## Calendar pad

Sparse golden calendars (monthly bars) need a sentinel day **strictly after**
`end_date` so Qlib's closed-interval `get_step_time` can resolve the last bar.
`ensure_calendar_pad` appends natural days to `calendars/day.txt` before
`QlibRuntime.activate(force=True)`.

## Verify

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase3b_qlib_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3b_*.py -q \
  --confcutdir=tests/research_data
```

Exit code **2** if pyqlib / LightGBM unavailable.
