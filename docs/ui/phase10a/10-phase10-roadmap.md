# Phase 10 roadmap (aligned with baseline v2)

## Done in this slice

- **10A** — SSOT audit docs under `docs/ui/phase10a/`
- **10B** — `GET /api/research/*` read DTOs (`app/services/research_data/research_query/`, `app/routes/research_read.py`)
- **10C** — Shell grouping (`src/config/shell-menu.js`, `BasicLayout` menus, `QuantShell/PageHeader`)
- **10D** — Read-only Research UI (datasets, alpha factors, models) + product status dashboard
- **10E** — Minimal 9G: experiment list/get + `POST /api/research/experiments` register

## Next (not in this slice)

- **10F** — Factor mining / library / training write UI
- **10G** — Phase 8 tabs inside Strategy Center
- **10H** — Trading / live depth
- **10I** — Full-chain acceptance

## Hard rules (unchanged)

- No fake POST for 9A–9F training/materialization
- `/api/factors` ≠ Phase 9 alpha factors (`/api/research/alpha-factors`)
- No Workspace “Run Experiment” until ExperimentRun pipeline is SSOT
