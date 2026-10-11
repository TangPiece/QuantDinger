# Phase 10 roadmap

## Done

- **10A** — SSOT audit docs under `docs/ui/phase10a/`
- **10B** — `GET /api/research/*` read DTOs (`research_query/`, `research_read.py`)
- **10C** — Shell grouping (`shell-menu.js`, `BasicLayout`, `QuantShell/PageHeader`)
- **10D** — Read-only Research UI (datasets, alpha factors, models) + product status
- **10E** — Experiment list/get only（register POST 已在 10B-R 冻结）
- **10F-1** — Factor Detail tabs + Evaluation read DTO（无 Mock）；Dataset 锚点只读

## Current：10B-R Real Research Data

文档：[`docs/ui/phase10b-r/`](../phase10b-r/)

- 源码 Real Data Gap Audit — COMPLETE  
- Experiment `POST /api/research/experiments` → **409 `experiment.writeFrozen`**  
- Runtime Canonical Probe — 暂缓  
- **R1** — Canonical → `list_data_versions` → Snapshot Assembler → `build_and_register` → 同 Registry → UI（门控 Probe）

## Next（依赖顺序，见 10B-R 02）

- **R1** Dataset 真实链（禁止 Golden 冒充）
- **R2–R5** FeatureSet / Factor / Evaluation / Library / Portfolio write API
- **R6–R7** Model train+artifact 统一事实源；修 Model/Artifact/Eval Read Bridge
- **R8** Experiment SSOT（解冻 POST）
- Strategy / Trading / Full E2E — 更后

## Hard rules

- 不为 UI 空白 Mock / INSERT / Golden 冒充生产
- `/api/factors` ≠ Phase 9 alpha factors（`/api/research/alpha-factors`）
- 无 ExperimentRun pipeline 不解冻 Experiment 写入口
- Model ACTIVE ≠ Strategy LIVE
