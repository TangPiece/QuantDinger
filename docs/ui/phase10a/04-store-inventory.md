# Phase 10A — Vuex store inventory

Root: `QuantDinger-Vue/src/store/`

| Module | Role | Phase 10 |
|--------|------|----------|
| `modules/async-router.js` | Dynamic routes from `router.config.js` | Unchanged; new routes auto-registered |
| `modules/user.js` | Auth, profile | Unchanged |
| `modules/app.js` | Theme, layout, multi-tab | Shell uses layout + grouped menus |
| `modules/policy.js` | Broker/policy | Unchanged |
| `modules/brand.js` | Branding | Unchanged |
| `modules/static-router.js` | Constant routes | Unchanged |

No dedicated Research store in Phase 10D — pages fetch via `src/api/research.js` locally (read-only browser pattern).
