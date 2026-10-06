# Phase 4I — Factor Portfolio

## Principle

```text
FactorDataset (+ 4C Evaluation forward returns)
  → PortfolioSpec
  → Rank / Select (top_n | top_pct | quantiles)
  → WeightGenerator (EQUAL | SCORE | RANK)
  → Rebalance (DAILY | WEEKLY | MONTHLY) + min_turnover
  → TargetPosition trajectory
  → Theoretical portfolio returns / risk / turnover
  → R2 qd/portfolio/{portfolio_hash}/ + D1 Summary
```

This is **Portfolio Construction** (目标持仓 + 理论绩效), not Production Backtest.

## vs 4E

| | 4E Groups | 4I Portfolio |
| --- | --- | --- |
| Question | 分组收益如何？ | 每天持什么？ |
| Input | `evaluation_hash` | `factor_dataset_id` + `evaluation_hash` |
| Output | group membership / group return | **TargetPosition + NAV metrics** |
| Rebalance | none | calendar + hold-forward |
| Weights | EQUAL only | EQUAL / SCORE / RANK |
| Cost | FIXED_BPS estimate | **none** (gross) |

## Package

```text
backend_api_python/app/services/research_data/factor_lab/portfolio/
```

API：`FactorPortfolioService`, `PortfolioSpec`, `compute_portfolio_hash`.

## Rules

| Item | Rule |
| --- | --- |
| Construction | `LONG_ONLY` / `LONG_SHORT` / `QUANTILE` |
| Selection | `TOP_N` or `TOP_PCT`；QUANTILE 用 `group_count`（Q1=最高） |
| LONG_SHORT | Long 权重和=+1，Short 和=−1 |
| Weights | EQUAL / SCORE / RANK（选定集合内归一） |
| Rebalance | DAILY / WEEKLY / MONTHLY；非调仓日 hold-forward |
| min_turnover | `0.5*Σ|Δw| < threshold` → 跳过调仓 |
| Returns | `Σ w_i * forward_return_hd`（缺失剔除后重标定）；gross |
| Direction | POSITIVE / NEGATIVE only（无 AUTO） |

## Storage

```text
qd/portfolio/{portfolio_hash}/
  positions/  weights/  returns/  turnover/
  metrics/summary.json
  summary.json  manifest.json
```

D1：`factor_portfolio`（[`0009_factor_portfolio.sql`](../../../workers/qd-research-d1/migrations/0009_factor_portfolio.sql)）仅 Summary。

## Acceptance

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4i_factor_portfolio.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4i_factor_portfolio.py -q \
  --confcutdir=tests/research_data
```

## Non-goals

```text
❌ Mean-Variance / Risk Parity / Black-Litterman / CVaR / RL
❌ Fees / Slippage / Limit-up / T+1 / Volume / Order Execution
❌ Production Backtest / Qlib Backtest
❌ Recompute Forward Return / Universe / PIT
❌ Modify 4C–4H engines / Level2 / signal/portfolio.py
❌ Detail positions in D1
❌ AUTO direction via IC
```
