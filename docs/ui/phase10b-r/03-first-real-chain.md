# 10B-R：第一条真实链（R1）验收说明

## 目标

让 `/research/datasets` 出现**第一条可追溯的真实 Dataset**，而非空态或假行。

## 正确链路（非表单直建）

```text
真实 Canonical
      ↓
DataVersion Discovery（ResearchRegistry.list_data_versions）
      ↓
Snapshot Assembler → snapshot_items（含 D1 所需 data_version_id）
      ↓
DatasetDefinition
      ↓
ResearchDatasetService.build_and_register()
      ↓
同一个 ResearchRegistry（Read API 所读之根）
      ↓
GET /api/research/datasets
      ↓
Vue Dataset List / Detail
```

## 明确禁止

- `INSERT` / Mock / seed 让 Product Status 变绿  
- `build_golden.py` / `use_fixture=True` / synthetic PIT·CA 进产品链  
- 仅传 Universe/Freq/Period/Features/Label 而**没有**真实 `snapshot_items` 的 “build” API  
- verify 脚本 temp 目录冒充 API 同根 cache

## R1 后端改造点

1. **`ResearchRegistry.list_data_versions(...)`**  
   LocalJson + D1：按 dataset_code / universe / window 发现已登记 DataVersion（uri、checksum、`data_version_id`）。

2. **Snapshot Assembler**  
   从 Discovery + 用户选择（Universe/Period 等）组装真实 `snapshot_items`；禁止 `golden_snapshot_items()`。

3. **Build 入口**  
   仅接受 Definition + Assembler 产出；调用既有 `build_and_register`；写入 Read API 同一 registry。

4. **Vue**  
   Dataset 构建 UI 绑定上述入口；List/Detail 继续只读展示哈希 / snapshot / PIT / price policy。

## Runtime Probe（门控；当前暂缓）

探针项（配置就绪后执行，密钥不入库）：

| 项 | 说明 |
|----|------|
| `QD_CANONICAL_PREFIX` / R2 | 是否存在 `qd/canonical/market|fundamental|universe/...` |
| `D1_RESEARCH_WORKER_URL` | D1 research worker 是否可达 |
| `QD_RESEARCH_CACHE_DIR` | 与 API 进程同根 |
| Registry 根 vs ModelPlatform 根 | 是否双事实源 |

本地曾观察到：`~/.quantdinger/cache/qd/` 下有 dataset/evaluation 等，**未必有** `canonical/`。  
**`HAS_REAL_CANONICAL` 未在本切片断言为 yes。**

## 验收清单（R1 完成后勾选）

- [ ] Discovery 能列出至少一条真实 DataVersion  
- [ ] Assembler 产出含合法 `data_version_id`（D1）或 LocalJson 等价 item  
- [ ] `build_and_register` 成功；`dataset_hash` / `snapshot_id` 非空  
- [ ] `GET /api/research/datasets` 可见该行  
- [ ] Vue List/Detail Overview 可见 hash / snapshot / PIT / price policy  
- [ ] 网络面板无假 IC / 假 preview 行  
- [ ] 产物可追溯到 Canonical DataVersion（非 Golden）
