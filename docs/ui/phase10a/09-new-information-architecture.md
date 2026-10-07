# Phase 10A — Target information architecture

Shell groups (sidebar):

```text
Dashboard     → /product-status
Research      → datasets, alpha factors, models, experiments; mining = coming soon
Strategy      → strategy-center (future: tabs for Phase 8)
Trading       → backtest-center, broker-accounts
AI & Dev      → ai-asset-analysis, indicator-community, indicator-ide, strategy-ide
Account       → billing, profile
Admin         → user-manage, agent-tokens, ai-skills, settings
```

Research domain tree (backend alignment):

```text
Research
├── Data (Datasets, Quality)        — 10D datasets detail tabs
├── Feature (Features)                — API 10B; UI TBD
├── Factor (Alpha, Library, Mining) — alpha-factors live; mining blocked
├── Model (Models, Lineage)         — 10D read-only
└── Experiment                        — 10E register; run pipeline later
```

Indicator domain stays under **AI & Dev**, not renamed to Factor.
