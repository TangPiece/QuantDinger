# Phase 10A — Route inventory (QuantDinger-Vue SSOT)

Source: `QuantDinger-Vue/src/config/router.config.js` (2026-03-26 audit).

## Async routes (authenticated shell)

| Path | Name | Visible | Notes |
|------|------|---------|-------|
| `/product-status` | ProductStatus | yes | Phase 10 dashboard v1 |
| `/research/datasets` | ResearchDatasets | yes | Read-only list |
| `/research/datasets/:id` | ResearchDatasetDetail | hidden | Detail |
| `/research/alpha-factors` | ResearchAlphaFactors | yes | 9B–9E alpha (not `/api/factors`) |
| `/research/alpha-factors/:id` | ResearchAlphaFactorDetail | hidden | |
| `/research/models` | ResearchModels | yes | Read-only |
| `/research/models/:id` | ResearchModelDetail | hidden | |
| `/research/experiments` | ResearchExperiments | yes | 9G register |
| `/research/experiments/:id` | ResearchExperimentDetail | hidden | |
| `/research/factor-mining` | ResearchFactorMining | yes | Disabled / Coming soon |
| `/ai-asset-analysis` | AIAssetAnalysis | yes | Landing (legacy default) |
| `/strategy-center` | StrategyCenter | yes | Live workspace |
| `/indicator-community` | IndicatorCommunity | yes | Marketplace |
| `/strategy-ide` | StrategyIDE | yes | |
| `/backtest-center` | BacktestCenter | yes | Strategy backtest (existing) |
| `/indicator-ide` | IndicatorIDE | yes | Technical indicators |
| `/universe-manager` | UniverseManager | hidden | |
| `/broker-accounts` | BrokerAccounts | yes | |
| `/billing` | Billing | yes | |
| `/profile` | Profile | yes | |
| `/user-manage` | UserManage | admin | |
| `/agent-tokens` | AgentTokens | admin | |
| `/ai-skills` | AiSkills | admin | |
| `/settings` | Settings | admin | |

## Redirects / legacy

| Path | Target |
|------|--------|
| `/` (app) | `/product-status` |
| `/dashboard` | `/strategy-center` |
| `/portfolio` | `/strategy-center` |
| `/indicator-analysis` | `/indicator-ide` |
| `/ai-analysis/*` | `/ai-asset-analysis` |
| `/strategy-runtime` | `/strategy-center` + query |

## Constant routes

| Path | Purpose |
|------|---------|
| `/user/login` | Auth |
| `/report/share/:token` | Public report |
| `/404` | Not found |

## Not in local router (README-only / deprecated)

- `trading-assistant`, `trading-bot`, standalone `portfolio`, standalone `dashboard` KPI — **not present** as first-class routes.
