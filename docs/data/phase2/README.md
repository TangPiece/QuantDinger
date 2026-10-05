# Phase 2 — Qlib Adapter & Research Engine

> **Status:** Phase 2E implemented (Prediction & Signal).
> 2F Experiment & Reproducibility remains next.

## Reading order

1. [01_qlib_adapter_core.md](01_qlib_adapter_core.md) — QlibRuntime / Dataset / Feature / Processor / VersionResolver
2. [02_dataset_handler.md](02_dataset_handler.md) — QuantDingerQLibHandler / segments / label / dataset cache
3. [03_processor_pipeline.md](03_processor_pipeline.md) — Processor whitelist / fit-on-train / pipeline digest
4. [04_model_training.md](04_model_training.md) — LightGBM train / artifact / prediction traceability
5. [05_prediction_signal.md](05_prediction_signal.md) — Prediction → Signal → TargetPosition（不下单）

## Prerequisite

Phase 1A–1D data foundation must PASS (see [../phase1/README.md](../phase1/README.md)).
