# Phase 10A — Route migration (current → target)

## Applied in Phase 10 slice

| Before | After |
|--------|-------|
| App redirect `/ai-asset-analysis` | `/product-status` |
| No research routes | `/research/datasets`, `/research/alpha-factors`, `/research/models`, `/research/experiments` |
| Flat sidebar | Grouped menus via `shellGroup` + `buildGroupedMenus` |

## Planned (10F–10G)

| Item | Target |
|------|--------|
| Strategy lifecycle tabs | Sub-routes or tabs under `/strategy-center` only |
| Research features list UI | `/research/features` (API ready) |
| Factor library / portfolios UI | `/research/factor-library` |
| Research backtest | New route; distinct from `/backtest-center` |

## Do not restore

- `/portfolio` as primary nav (keep redirect to strategy-center)
- README `trading-assistant` / `trading-bot` as top-level without implementation
