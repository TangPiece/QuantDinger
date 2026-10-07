# Phase 10A — View inventory

Root: `QuantDinger-Vue/src/views/`

## Product / Research (Phase 10)

| View | Path |
|------|------|
| Product status | `product-dashboard/index.vue` |
| Dataset list/detail | `research/datasets/List.vue`, `Detail.vue` |
| Alpha factor list/detail | `research/alpha-factors/List.vue`, `Detail.vue` |
| Model list/detail | `research/models/List.vue`, `Detail.vue` |
| Experiment list/detail | `research/experiments/List.vue`, `Detail.vue` |
| Coming soon placeholder | `research/ComingSoon.vue` |

## Strategy / trading / AI (existing)

| Area | Entry |
|------|--------|
| Strategy center | `strategy-center/index.vue` + components |
| Strategy IDE | `strategy-ide/index.vue` |
| Backtest | `backtest-center/index.vue`, `FactorResearchResult.vue` |
| Indicator IDE | `indicator-ide/index.vue` |
| Indicator community | `indicator-community/index.vue` |
| Broker | `broker-accounts/index.vue` |
| AI asset analysis | `ai-asset-analysis/index.vue` |
| Admin | `user-manage`, `agent-tokens`, `ai-skills`, `settings` |

## Orphan / hidden

- `executor-strategies/index.vue` — not in `router.config.js`
- `ai-analysis/index.vue` — superseded by redirects to ai-asset-analysis
- `indicator-analysis/` — legacy chart; route redirects to indicator-ide
