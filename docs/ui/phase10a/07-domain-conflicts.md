# Phase 10A — Domain naming conflicts

## Factor (three meanings)

| Name in UI/API | Meaning | Action |
|----------------|---------|--------|
| `/api/factors`, Agent `/research/factors` | Built-in + TALib indicator catalog | Keep under **Indicator**; never map to 9E |
| `backtest-center/FactorResearchResult.vue` | IC research on catalog factors | Legacy; separate from alpha factor platform |
| `/api/research/alpha-factors` | Registry `FeatureDefinition` / 9B–9E alpha | **Research → Factors** |

## Indicator vs Feature vs Factor

- **Indicator IDE** — trading/chart scripts (`indicator-ide`, community)
- **Feature** — research data features (`GET /api/research/features`)
- **Factor** — evaluated alpha (`alpha-factors`)
- **Model** — 9F lifecycle (`/api/research/models`); ACTIVE ≠ Strategy LIVE

## Backtest

- **Backtest Center** — existing strategy V2 backtest (`/api/backtest`)
- **Research backtest / experiment run** — blocked until 9G run SSOT

## Dashboard

- Old `/dashboard` → strategy-center redirect
- New **Product Status** — `/product-status`, no fake aggregate KPIs
