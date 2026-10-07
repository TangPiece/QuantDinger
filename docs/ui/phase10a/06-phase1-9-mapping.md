# Phase 10A — UI × Phase 1–9 Capability Matrix

| Local module | Route | Current API | Capability | Phase | Domain | Action | API dep |
|--------------|-------|-------------|------------|-------|--------|--------|---------|
| product-status | `/product-status` | `GET /api/research/product-status` | Maturity dashboard | 10 | Dashboard | NEW | 10B |
| research/datasets | `/research/datasets` | `GET /api/research/datasets` | Dataset browser | 9A | Research/Data | NEW | 10B |
| research/alpha-factors | `/research/alpha-factors` | `GET /api/research/alpha-factors` | Alpha factor browser | 9B–9E | Research/Factor | NEW | 10B |
| research/models | `/research/models` | `GET /api/research/models` | Model browser | 9F | Research/Model | NEW | 10B |
| research/experiments | `/research/experiments` | `GET/POST /api/research/experiments` | Experiment SSOT | 9G | Research/Experiment | NEW | 10E |
| research/factor-mining | `/research/factor-mining` | — | Mining UI | 9D | Research/Factor | BLOCKED | 10F |
| strategy-center | `/strategy-center` | `/api/strategies/*` | Live + ops | 8 + existing | Strategy | REFACTOR |已有 |
| strategy-ide | `/strategy-ide` | `/api/strategies/*` | Script lab | existing | AI/Strategy | KEEP |已有 |
| indicator-ide | `/indicator-ide` | `/api/indicator/*` | Indicator scripts | existing | AI/Indicator | KEEP |已有 |
| indicator-community | `/indicator-community` | `/api/community/*` | Marketplace | existing | AI/Indicator | KEEP |已有 |
| backtest-center | `/backtest-center` | `/api/backtest/*` | Strategy backtest | 4 | Trading/Research | KEEP |已有 |
| broker-accounts | `/broker-accounts` | `/api/alpaca/*`, IBKR | Broker | 6/7 | Trading | KEEP |已有 |
| ai-asset-analysis | `/ai-asset-analysis` | market modules | AI landing | existing | AI | KEEP |已有 |
| factor.js (Vue) | — | `/api/factors` | TALib / catalog | legacy | Indicator | ISOLATE |已有 |
| agent research | — | `/api/agent/v1/research/factors` | Agent TALib | legacy | Indicator | ISOLATE |已有 |
| universe-manager | hidden | `/api/universes` | PIT universes | existing | Research adj. | KEEP |已有 |

Action legend: `KEEP | REFACTOR | MOVE | MERGE | DEPRECATE | NEW | BLOCKED`

API dep legend: `已有 HTTP | 10B | 9G | Mock Only`
