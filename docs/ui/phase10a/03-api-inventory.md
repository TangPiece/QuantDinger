# Phase 10A — API inventory (Vue client)

Root: `QuantDinger-Vue/src/api/`

| Module | Base paths | Phase 10 note |
|--------|------------|---------------|
| `research.js` | `/api/research/*` | **10B** read + experiment register |
| `factor.js` | `/api/factors` | Legacy TALib — **do not** wire to Research alpha UI |
| `agent.js` | `/api/agent/v1/*` | Agent gateway; `/research/factors` is old catalog |
| `strategy.js` | `/api/strategies`, `/api/backtest` | Strategy + backtest center |
| `universe.js` | `/api/universes` | Universe manager |
| `broker.js` | `/api/alpaca`, IBKR | Broker accounts |
| `market.js`, `global-market.js`, `marketModules.js` | market | AI asset page |
| `portfolio.js` | `/api/portfolio` | Hidden route; API still present |
| `auth.js`, `user.js`, `billing.js`, `settings.js` | admin/account | Shell account/admin groups |

Backend Phase 9 domain remains Service/LocalJson; **product** exposure for research is only via `/api/research` (10B), not raw registry JSON.
