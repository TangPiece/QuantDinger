# Phase 5E — Qlib ↔ QuantDinger Cross Validation

> **Status:** Implemented. Dual-engine consistency for Research QD (5B) vs Research Qlib (5D).
> Not Production. Not “returns must always match” — **differences must be attributable**.

## Boundary

```text
Same strategy_hash + Snapshot + window
  → 5B ResearchBacktest (QuantDinger)
  → 5D QlibStrategyService (Qlib)
  → cross_validation Diff Engine L1–L7
  → CrossValidationReport + Attribution → R2 + D1 0014
```

Package: `app/services/research_data/cross_validation/`  
（与 Phase 3E `backtest_consistency/` **并列**：3E 比 Qlib Research vs **Production**；5E 比 Research QD vs Research Qlib。）

## Principles

1. **相同语义 → 结果一致；不同语义 → 差异可解释。**
2. **Baseline 先过**：默认 `realism=GROSS`（零成本）+ 同一 TargetPosition + 同一 bars + `NEXT_OPEN`。
3. 严格复用 5A–5D Contract / Hash / Snapshot；不改 Strategy Contract。
4. Domain 禁止 `import qlib` / `ProductionBacktestEngine`。

## DiffKind

| Kind | 含义 |
| --- | --- |
| EXACT | 集合/身份必须全等 |
| NUMERIC | float 容差 |
| SEMANTIC | 执行日 / fill 规则 |
| EXPECTED_DIFFERENCE | 已知引擎差（读 5D compatibility） |
| UNSUPPORTED | 一侧无能力 |

## Layers (L1–L7)

| Layer | Kind (GROSS) | 源 |
| --- | --- | --- |
| Dataset | EXACT | materialization_id / dataset_hash / bars 质量 |
| PIT | EXACT | available≤knowledge；look-ahead / leakage |
| Universe | EXACT | snapshot_id + membership |
| Signal | NUMERIC | 5A signals vs prediction/scores.json |
| Portfolio | NUMERIC | TargetPosition vs weights/weights.json |
| Execution | SEMANTIC | policy + compatibility |
| NAV | NUMERIC | 5B portfolio vs 5D `nav/daily.json` |
| Performance | NUMERIC | metrics_json 对照 |

NET：成本 / T+1 → EXPECTED_DIFFERENCE / UNSUPPORTED（不强制收益相等）。

## Attribution

```text
delta_return ≈ data + signal + portfolio + execution + cost + other
```

GROSS 下 L1–L5 PASS 时前三项为 0；残余归 execution（fill 语义）。  
`|other|` 超容差且无解释 → `FAILED`。

Status：`PASSED` | `PASSED_WITH_EXPECTED_DIFF` | `FAILED`。

## Storage

```text
qd/cross_validation/{cv_hash}/
  report.json
  layers/*.json
  nav_diff.json
  attribution.json
  summary.json
  manifest.json
```

D1：`0014_cross_validation.sql` → `research_cross_validation`（PK `cv_hash`）。

5D 为本阶段启用：`qd/qlib_run/{hash}/nav/daily.json` + `backtest_hash` 配对字段。

## API

```python
from app.services.research_data.cross_validation import (
    CrossValidationService,
    CrossValidationSpec,
)

result = CrossValidationService(store, registry).run(
    strategy_hash,
    CrossValidationSpec(
        strategy_hash=strategy_hash,
        start_date=...,
        end_date=...,
        realism="GROSS",
    ),
    metadata={
        "targets_by_date": {...},
        "signal_rows": [...],
        "price_bars": [...],
        "universe_membership": [...],
        "snapshot_id": "...",
        "force_recompute": True,
    },
)
# result.report.status / layers / attribution / side_by_side
```

## CLI

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/qd_research_validate.py --golden

QUANTDINGER_SKIP_APP_INIT=1 python scripts/qd_research_validate.py \
  --strategy-hash <hash> --start 2022-01-01 --end 2022-06-01 --realism GROSS
```

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5e_cross_validation.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5e_cross_validation.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Merge with Phase 3E Production consistency
❌ Force Qlib NET == QD NET
❌ Modify Strategy Contract / Qlib source
❌ Production / Live / 5F Bridge
❌ P1 multi-market / CA / Level2
❌ P2 CI dashboard / visualization
```
