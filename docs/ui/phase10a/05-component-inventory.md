# Phase 10A — Component inventory (Phase 10 relevant)

## New (Phase 10C/D)

| Component | Path |
|-----------|------|
| Page header / breadcrumb | `src/components/QuantShell/PageHeader.vue` |
| Shell menu builder | `src/config/shell-menu.js` |

## Reused layout

| Component | Path |
|-----------|------|
| BasicLayout (grouped menus) | `src/layouts/BasicLayout.vue` |
| RouteView (keep-alive host) | `src/layouts/RouteView.vue` |
| Pro layout, MultiTab, SettingDrawer | `src/components/*` |

## Domain-heavy existing (unchanged)

- Strategy center tables/editors — `views/strategy-center/components/*`
- Backtest panels — `components/BacktestAssumptionsPanel.vue`, backtest-center views
- Indicator IDE / community cards — `views/indicator-*`

Research list/detail pages use Ant Design Vue `a-table`, `a-descriptions`, `a-tabs` only — no shared Research workspace component yet (intentionally deferred until 9G run SSOT).
