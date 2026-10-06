# Phase 5D — Qlib Strategy Adapter

> **Status:** Implemented. Swappable Research Engine over 5A Strategy Contract.
> Qlib is **not** Domain SSOT and **not** Production Backtest.

## Boundary

```text
5A strategy_hash → TargetPosition / Signal
  → qlib_strategy adapters (dataset / signal / portfolio / execution)
  → Qlib cache (1C Materializer via 2A ensure_cache)
  → QuantDingerWeightStrategy + exchange_kwargs (3B)
  → spawn subprocess: qlib.init → backtest → exit
  → QlibRunSummary (R2 + D1) comparable to 5B frames
```

Package: `app/services/research_data/qlib_strategy/`  
（与 Phase 2A `qlib_adapter/` 并列；策略逻辑不塞进 Dataset Adapter。）

## Principles

- **Strategy Contract 不变**：只消费 5A Signal / TargetPosition。
- **v1 唯一执行路径**：WeightStrategy from TargetPosition；不启用 Qlib 原生 TopK 重选。
- **Dataset**：复用 `QlibAdapter.ensure_cache` / 1C Materializer，不新建转换。
- **进程隔离**：默认 `multiprocessing` spawn；仅 `worker_main.py` 可 `import qlib`。
- **ExecutionCompatibility**：写入 Summary；NET 必含 PARTIAL/UNSUPPORTED，禁止静默声称与 5C 完全一致。

## ExecutionCompatibility

| 能力 | Level | 说明 |
| --- | --- | --- |
| Weight from TargetPosition | SUPPORTED | 主路径 |
| NEXT_OPEN / deal_price open\|close | SUPPORTED | 经 `exchange_map` |
| Commission / stamp / slippage / min_cost / lot | PARTIAL (NET) | Qlib 简化双边成本 ≠ 5C T+1 账本 |
| T+1 sellable / OrderIntent path | UNSUPPORTED | 差异由 5E 解释 |
| Limit up/down / suspend | PARTIAL (NET) | `limit_threshold` 近似 |
| TWAP/VWAP / Level2 | UNSUPPORTED | |
| Native Qlib TopkDropout re-select | UNSUPPORTED | v1 不启用 |

`realism=GROSS`：以无成本可比为主。`NET`：compatibility 中 PARTIAL/UNSUPPORTED 必填。

## Spec / Hash / Storage

`QlibStrategySpec`：`strategy_hash`、窗口、`execution_policy`、`realism`、`market_rule`、`dataset_ref` / `materialization_id`、`qlib_engine_version=qlib_strategy_adapter@1`、`region`。

`qlib_run_hash` = sha256(strategy_hash + window + execution_policy + realism + market_rule + cost fingerprint if NET + materialization + engine_version + region)。

```text
qd/qlib_run/{qlib_run_hash}/
  prediction/
  weights/
  metrics/summary.json
  compatibility.json
  manifest.json
```

D1：`0013_qlib_strategy.sql` → `research_qlib_run`（PK `qlib_run_hash`）。

## API

```python
from app.services.research_data.qlib_strategy import (
    QlibStrategyService,
    QlibStrategySpec,
)

result = QlibStrategyService(store, registry).run(
    strategy_hash,
    QlibStrategySpec(
        strategy_hash=strategy_hash,
        start_date=...,
        end_date=...,
        realism="GROSS",  # or NET
        market_rule="CN_A",
    ),
    metadata={
        # 测试注入：targets_by_date / signal_rows / price_bars
        # force_inprocess / force_synthetic / skip_ensure_cache
        "force_recompute": True,
    },
)
# result.summary → QlibRunSummary（metrics_json + compatibility_json）
```

无 pyqlib / 无 cache 时，runner 可走 `synthetic_weight_nav`（CI / verify 默认）；有 pyqlib 且 cache 就绪时 spawn `worker_main` 跑真实 `qlib.init` backtest。

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5d_qlib_strategy.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5d_qlib_strategy.py -q \
  --confcutdir=tests/research_data
```

Golden 四层：数据映射 / Signal / Portfolio 权重 / GROSS 收益方向；静态 AST 隔离 Domain 不得 `import qlib`。

## Non-goals

```text
❌ Modify Qlib source / Strategy Contract
❌ Qlib as Domain SSOT or Production Backtest
❌ Expose qlib.strategy.* types in Domain exports
❌ Native Topk re-selection changing QD portfolio
❌ Full 5E diff attribution engine
❌ Broker / live / RL / Level2
```

## 5E 预留

同一 `strategy_hash` + 窗口产出可比 `metrics_json` + `compatibility_json`，供跨引擎差异归因。
