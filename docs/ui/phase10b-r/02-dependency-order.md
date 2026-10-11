# 10B-R：依赖顺序（下一刀只切一环）

## 硬规则

1. Vue 是最后一层；不为 UI 空白造假数据。
2. 每环必须：真实产生 → Registry/Artifact → Read API → UI。
3. 禁止跨环抢跑（例如无 Dataset 就造 Model ACTIVE）。
4. Golden / fixture / synthetic PIT·CA ≠ 生产。

## 严格顺序

```text
① Canonical（真实源 / Writer）
② DataVersion Discovery（list_data_versions）
③ Snapshot Assembler → snapshot_items
④ DatasetDefinition + build_and_register
⑤ FeatureSet / FeatureVersion
⑥ Factor Definition + Materialization
⑦ Factor Evaluation（真实 run）
⑧ Factor Library（promotion gate）
⑨ Factor Portfolio
⑩ Model TrainingRun + Artifact
⑪ Model Evaluation（真 Service）
⑫ Approval / Activation
⑬ Experiment SSOT（有 Run 才解冻 POST）
⑭ Backtest / Strategy Candidate
```

## 切片排期

| Slice | 内容 | 前置 |
|-------|------|------|
| 10B-R 冻结 | Experiment POST → 409；文档入库 | 审计完成 |
| Runtime Probe | 本机 R2/D1/`qd/canonical` 探针 | 运行配置就绪（可暂缓） |
| **R1** | Discovery + Snapshot Assembler + 真实 Dataset 进同 Registry + Read/UI | Probe 确认有真实 Canonical |
| R2 | FeatureSet / Factor materialize API | R1 绿 |
| R3 | Factor Evaluation trigger API | R2 |
| R4 | Library promote API | R3 |
| R5 | Portfolio | R4 |
| R6 | Training + Artifact 统一事实源 | R5 |
| R7 | 修 Model/Artifact/Eval Read Bridge | R6 |
| R8 | Experiment SSOT（解冻） | R7 |

## 当前停点

- 审计文档：COMPLETE  
- Experiment 假登记：冻结（见 `research_read.py`）  
- Runtime Probe：暂缓  
- R1：门控在 Probe（有真实 Canonical 后才开）
