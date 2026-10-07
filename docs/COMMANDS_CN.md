# QuantDinger 命令

在仓库根目录执行，除非某一节写明要先进入 `backend_api_python`。Level2 明细和因子都在 `backend_api_python/data/`，不进 git。

研究数据平台 Phase 1 契约（D1 `qd_research` / R2 Canonical / DataQuery，设计稿）：见 [docs/data/phase1/README.md](data/phase1/README.md)。

| 目录 | 内容 |
| --- | --- |
| `data/level2_raw` | 原始 `.7z` 和已解压的 CSV |
| `data/level2_staging/parquet` | 转换后的三类明细 |
| `data/level2_staging/factors` | 批量因子断点标记（`_done` / `_uploaded`）；日宽表发布到 D1 后删除 |
| `data/level2_parquet` | 图表临时下载的明细，算完会删 |
| `data/level2_factor_markers` | 图表补数断点标记目录（非读侧真源） |

因子云端真源是 **Cloudflare D1**（经 `workers/l2-factors-d1` Worker）；图表/回测只读 D1。明细仍可走 R2/百度。

## 安装和运行

| 命令 | 作用 | 改数据 |
| --- | --- | --- |
| `./install.sh` | Linux/macOS 交互安装 | 会写本机配置和容器 |
| `./install.ps1` | Windows 交互安装 | 会写本机配置和容器 |
| `docker compose up -d --build` | 构建并启动本机服务 | 会写数据库和数据卷 |
| `docker compose ps` | 查看容器状态 | 否 |
| `curl -sS http://127.0.0.1:5000/api/health` | 后端健康检查 | 否 |
| `docker compose -f docker-compose.yml -f docker-compose.production.yml up -d` | 按生产叠加层启动 | 会写数据库和数据卷 |
| `python backend_api_python/scripts/check_production_config.py` | 拒绝已知的不安全生产默认值 | 否 |

网页默认在 `http://127.0.0.1:8888`，接口在 `http://127.0.0.1:5000`。

## 研究 Registry D1 Worker（qd_research）

在 `workers/qd-research-d1`（与 Level2 `l2_factors` **独立**）：

```bash
cd workers/qd-research-d1
npm install
npx wrangler d1 create qd_research
# 把 database_id 写入 wrangler.toml
npx wrangler d1 migrations apply qd_research --remote
echo -n '<随机 token>' | npx wrangler secret put WORKER_TOKEN
npx wrangler deploy
```

```
D1_RESEARCH_WORKER_URL=https://qd-research-d1.<account>.workers.dev
D1_RESEARCH_WORKER_TOKEN=<随机 token>
QD_CANONICAL_PREFIX=qd
```

导出 PG Universe → 研究 Snapshot（默认写本地 Canonical；加 `--use-r2` 写 R2）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/export_universe_snapshot.py \
  --universe-code CSI300 --version 2026.10.05 --start 2020-01-01
```

构建 Golden Dataset `cn_stock_daily@v1`（默认 fixture / 本地 Canonical；`--from-source` 拉真源；`--use-r2` 写 R2）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/build_golden_dataset.py \
  --start 2020-01-01 --end 2025-12-31
```

物化 Qlib 派生缓存（经 DataQuery；`--wipe` 删后重建）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/materialize_qlib_dataset.py \
  --dataset-ref cn_stock_daily@v1 --wipe
```

验证 Qlib Cache 真读回 / Phase 1D 六项一致性（Canonical → Materializer → pyqlib）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase1d_consistency.py
# 兼容别名：python scripts/verify_qlib_cache_readback.py
```

本地单测：`cd workers/qd-research-d1 && npm test`；`cd backend_api_python && python -m pytest tests/research_data -q`。

Phase 1B 验收报告：[docs/data/phase1/07_phase1b_validation.md](data/phase1/07_phase1b_validation.md)。
Phase 1C 物化说明：[docs/data/phase1/08_qlib_materialization.md](data/phase1/08_qlib_materialization.md)。
Phase 1D 读回一致性：[docs/data/phase1/09_qlib_read_validation.md](data/phase1/09_qlib_read_validation.md)。

验证 Phase 2A Qlib Adapter Core（Runtime / Handler / bundle_hash）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2a_adapter.py
```

Phase 2A 说明：[docs/data/phase2/01_qlib_adapter_core.md](data/phase2/01_qlib_adapter_core.md)。

验证 Phase 2B Dataset / Handler（segments / label / dataset-cache）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2b_dataset.py
```

Phase 2B 说明：[docs/data/phase2/02_dataset_handler.md](data/phase2/02_dataset_handler.md)。

验证 Phase 2C Processor Pipeline（fit / hash / `qd_standard@1`）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2c_processor.py
```

Phase 2C 说明：[docs/data/phase2/03_processor_pipeline.md](data/phase2/03_processor_pipeline.md)。

验证 Phase 2D Model Training（LightGBM / artifact / prediction 追溯）：

```bash
cd backend_api_python
# macOS 无 brew 且 import lightgbm 报 libomp：
#   ./scripts/bootstrap_lightgbm_libomp_macos.sh .test_deps/py312/bin/python
# 有 Homebrew：brew install libomp
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2d_model.py
```

Phase 2D 说明：[docs/data/phase2/04_model_training.md](data/phase2/04_model_training.md)。

验证 Phase 2E Prediction & Signal（合成 Prediction → Signal → TargetPosition，无需 LightGBM）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase2e_signal.py
```

Phase 2E 说明：[docs/data/phase2/05_prediction_signal.md](data/phase2/05_prediction_signal.md)。

验证 Phase 2F Experiment & Reproducibility（双跑复现 / manifest / MLflow）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase2f_experiment.py
```

Phase 2F 说明：[docs/data/phase2/06_experiment_reproducibility.md](data/phase2/06_experiment_reproducibility.md)。Phase 2 到此结束。

验证 Phase 3A Backtest Contract（契约 / 预设 / 无 qlib）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3a_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3a_*.py -q \
  --confcutdir=tests/research_data
```

Phase 3A 说明：[docs/backtest/README.md](backtest/README.md)、[docs/data/phase3/README.md](data/phase3/README.md)。

验证 Phase 3B Qlib Research Backtest（需 pyqlib + LightGBM；缺依赖退出码 2）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_phase3b_qlib_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3b_*.py -q \
  --confcutdir=tests/research_data
```

Phase 3B 说明：[docs/backtest/07_qlib_research_backtest.md](backtest/07_qlib_research_backtest.md)。

验证 Phase 3C Trading Cost & Execution Rules（无 qlib）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3c_execution_rules.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3c_*.py -q \
  --confcutdir=tests/research_data
```

Phase 3C 说明：[docs/backtest/08_trading_cost_execution.md](backtest/08_trading_cost_execution.md)。

验证 Phase 3D Production Backtest（无 qlib；组合 3C ExecutionSimulator）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3d_production_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3d_*.py -q \
  --confcutdir=tests/research_data
```

Phase 3D 说明：[docs/backtest/09_production_backtest.md](backtest/09_production_backtest.md)。

验证 Phase 3E Dual Engine Consistency（Golden；缺 pyqlib 时双引擎跳过，Production 阶梯仍跑）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase3e_consistency.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase3e_*.py -q \
  --confcutdir=tests/research_data
```

Phase 3E 说明：[docs/backtest/06_dual_engine_consistency.md](backtest/06_dual_engine_consistency.md)。

验证 Phase 4A Factor Lab Foundation（定义 / 版本不可变 / hash / Dataset Manifest）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4a_factor_lab.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase4a_*.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4B Factor Computation（DAG / ComputePlan / PIT / 多引擎 / 不可变 Dataset）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4b_factor_compute.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4b_factor_compute.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4C Factor Evaluation（EvaluationSpec / ForwardReturn / Universe Snapshot / SampleStatus；无 IC）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4c_factor_evaluation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4c_factor_evaluation.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4D IC / RankIC / ICIR（按日横截面；不重算 Forward Return）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4d_factor_metrics.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4d_factor_metrics.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4E Group Return / Turnover / Cost（等权分位；非 Production Backtest）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4e_factor_groups.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4e_factor_groups.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4F Stability / Decay（Rolling IC、Decay、Regime；无 look-ahead）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4f_factor_stability.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4f_factor_stability.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4G Factor Neutralization（OLS residual；Raw 不可变；可再进 4C）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4g_factor_neutralization.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4g_factor_neutralization.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4H Factor Combination（对齐/标准化/相关/加权/正交；成员不可变；Composite 可再进 4C）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4h_factor_combination.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4h_factor_combination.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 4I Factor Portfolio（选股/权重/调仓/理论绩效；TargetPosition；无撮合成本）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase4i_factor_portfolio.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase4i_factor_portfolio.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 5A Strategy Research（Strategy Contract；Signal + TargetPosition；PIT/look-ahead；不算收益）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5a_strategy_research.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5a_strategy_research.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 5B Research Backtest（消费 5A TargetPosition；NEXT_OPEN/NoCost；NAV/绩效/基准；不撮合）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5b_research_backtest.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5b_research_backtest.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 5C Cost & Execution（NET 路径；CN_A 成本/约束；Gross→Net 归因；不调用 Production）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5c_research_execution.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5c_research_execution.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 5D Qlib Strategy Adapter（5A→Qlib 适配；WeightStrategy；ExecutionCompatibility；spawn 隔离；无 pyqlib 走合成路径）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5d_qlib_strategy.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5d_qlib_strategy.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 5E Cross Validation（同一 strategy_hash；L1–L7 Diff + 归因；GROSS baseline；NET 可解释差异）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5e_cross_validation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/qd_research_validate.py --golden

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5e_cross_validation.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 5F Production Bridge（冻结 Bundle；状态机；Feature parity；Gate；干跑 Inference→OrderIntent；回滚；不接 Broker）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase5f_production_bridge.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase5f_production_bridge.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6A Production Runtime（DEPLOYED Bundle；TradingSession；Online Feature→5F infer→OrderIntent；幂等；PAPER/SHADOW；不接 Broker）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6a_production_runtime.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6a_production_runtime.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6B Portfolio Service（Account/Position；available/frozen；Event→Reducer→Snapshot；Target→Delta；PAPER Fill；CA/对账契约；不接 Broker）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6b_portfolio_service.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6b_portfolio_service.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6C Risk Engine（Policy@version；可组合规则；MODIFY 只减不增；→OrderIntent；幂等；不接 OMS/Broker）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6c_risk_engine.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6c_risk_engine.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6D OMS（OrderIntent→Order 状态机；幂等/client_order_id；Partial/Cancel/Replace/UNKNOWN；Outbox+Paper；Fill→6B；不接真实 Broker/pending_orders）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6d_oms.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6d_oms.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6E Broker Adapter（Contract；PaperBrokerAdapter；Fake REST/WS；BROKER_SUBMIT；dedup/UNKNOWN/WS 恢复；Reference=Alpaca Paper；禁止 LIVE / live_trading Domain）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6e_broker_adapter.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6e_broker_adapter.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6F Reconciliation（BrokerSnapshot；Order/Fill/Position/Cash/P&L；Finding 生命周期；CRITICAL → Trading Gate 阻断新单；CRITICAL 禁 Waive；禁止 live_trading / pending_orders / qlib）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6f_reconciliation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6f_reconciliation.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6G Safety（Fail-Closed Gate；Kill Switch；6F CRITICAL ingest；UNKNOWN→BLOCK；重启 HALT 持久；禁止 live_trading / pending_orders / qlib）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  python scripts/verify_phase6g_safety.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6g_safety.py -q \
  --confcutdir=tests/research_data
```

验证 Phase 6H Ops（Health / Audit / Alert；trace_id；Incident；CRITICAL→Safety；WARNING 不 HALT；审计不可覆盖；禁止 live_trading / pending_orders / qlib）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase6h_ops.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6h_ops.py -q \
  --confcutdir=tests/research_data
```

### Phase 6I Paper / Shadow E2E

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase6i_e2e.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6i_e2e.py -q \
  --confcutdir=tests/research_data
```

### Phase 6J Production Readiness

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase6j_readiness.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase6j_readiness.py -q \
  --confcutdir=tests/research_data
```

生产 runbook：[docs/production/](../production/)。24h Paper soak 入口（非门禁）：`scripts/soak_paper_stub.py`。

### Phase 7A Live Read-only

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7a_live_readonly.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase7a_live_readonly.py -q \
  --confcutdir=tests/research_data
```

需真实 Alpaca Live **只读 GET** 时设置 `PRODUCTION_READY=true` 与 `ALPACA_LIVE_*`（见 `env.example`）。Phase 7 说明：[docs/data/phase7/README.md](data/phase7/README.md)。

### Phase 7B Live MD + Shadow Trading

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7b_shadow_trading.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase7b_shadow_trading.py -q \
  --confcutdir=tests/research_data
```

环境阶梯（7B）：`PAPER→SHADOW→LIVE_READONLY`；禁止 `PAPER→LIVE_READONLY`。真实 Alpaca **Data** GET（可选）需 `ALPACA_LIVE_DATA_URL=https://data.alpaca.markets` 与同组 `ALPACA_LIVE_*`。

### Phase 7C Controlled Live（单笔真实 LIMIT）

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7c_controlled_live.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase7c_controlled_live.py -q \
  --confcutdir=tests/research_data
```

仅 `LIVE_CONTROLLED` 可 submit；默认 `max_orders=1`（7D 可调多笔预算）；cancel/replace/MARKET/resubmit 均拒。CI 默认 Fake broker（0 次真实 POST）。真实 Alpaca POST 需 `CONTROLLED_LIVE_ALLOW_REAL_SUBMIT=true` 与 `ALPACA_LIVE_*`（见 `env.example`）。环境阶梯：`LIVE_READONLY→LIVE_CONTROLLED`（需 `PRODUCTION_READY`）。7D 起 FILLED 单笔不默认 kill session（见 [04_controlled_live_production.md](data/phase7/04_controlled_live_production.md)）。

### Phase 7D Controlled Live Production（持续 tick）

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7d_controlled_production.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase7d_controlled_production.py -q \
  --confcutdir=tests/research_data
```

### Phase 7E Gradual Scale（Trading Governance）

Fake registry 默认；`LIVE` 在 OMS 允许集合内但 **须** `governance_live_authorized` / Gateway 授权。说明：[05_gradual_scale.md](data/phase7/05_gradual_scale.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7e_gradual_scale.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase7e_gradual_scale.py -q \
  --confcutdir=tests/research_data
```

运维显式开启 LIVE 环境审批（勿提交密钥）：

```bash
export PRODUCTION_READY=true
export LIVE_ENV_APPROVAL=true
```

### Phase 8A Strategy Registry（身份 + 版本钉扎 SSOT）

Fake ProductionBundle + LocalJson 默认；说明：[01_strategy_registry.md](data/phase8/01_strategy_registry.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8a_strategy_registry.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8a_strategy_registry.py -q \
  --confcutdir=tests/research_data
```

### Phase 8B Strategy Candidate（Research → 可治理候选）

Fake Experiment/Backtest/StrategyResearch + LocalJson 默认；说明：[02_strategy_candidate.md](data/phase8/02_strategy_candidate.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8b_strategy_candidate.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8b_strategy_candidate.py -q \
  --confcutdir=tests/research_data
```

### Phase 8C Validation Gate（Candidate 准入审查）

Fake inject + LocalJson 默认；说明：[03_validation_gate.md](data/phase8/03_validation_gate.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8c_validation_gate.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8c_validation_gate.py -q \
  --confcutdir=tests/research_data
```

### Phase 8D Promotion Pipeline（环境晋升）

Fake inject + LocalJson 默认；说明：[04_promotion_pipeline.md](data/phase8/04_promotion_pipeline.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8d_promotion_pipeline.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8d_promotion_pipeline.py -q \
  --confcutdir=tests/research_data
```

### Phase 8E Live Performance Feedback（漂移观察）

Fake inject + LocalJson 默认；说明：[05_live_performance_feedback.md](data/phase8/05_live_performance_feedback.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8e_performance_feedback.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8e_performance_feedback.py -q \
  --confcutdir=tests/research_data
```

### Phase 8H Production → Research Feedback Loop

Fake inject + LocalJson 默认；说明：[08_production_research_feedback.md](data/phase8/08_production_research_feedback.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8h_production_research_feedback.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8h_production_research_feedback.py -q \
  --confcutdir=tests/research_data
```

### Phase 9A Research Dataset Platform

LocalJson + 本地/R2 artifact 布局；说明：[01_dataset_platform.md](data/phase9/01_dataset_platform.md)、路线：[phase9/README.md](data/phase9/README.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9a_dataset_platform.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9a_dataset_platform.py -q \
  --confcutdir=tests/research_data
```

### Phase 9B Feature / Factor Platform

复用 `factor_lab` 计算与 DAG；钉住 9A `DatasetHandle`；说明：[02_feature_factor_platform.md](data/phase9/02_feature_factor_platform.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9b_feature_factor_platform.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9b_feature_factor_platform.py -q \
  --confcutdir=tests/research_data
```

### Phase 9C Factor Evaluation Engine

钉住 9B build + 9A dataset；编排 4C–4F；说明：[03_factor_evaluation_engine.md](data/phase9/03_factor_evaluation_engine.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9c_factor_evaluation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9c_factor_evaluation.py -q \
  --confcutdir=tests/research_data
```

### Phase 9D Factor Mining

DSL 模板搜索 + Fast Screen + 9B/9C 编排；说明：[04_factor_mining.md](data/phase9/04_factor_mining.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9d_factor_mining.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9d_factor_mining.py -q \
  --confcutdir=tests/research_data
```

### Phase 9E Factor Library

Promotion Gate + Catalog/Tags + Collection/PortfolioSpec；说明：[05_factor_library.md](data/phase9/05_factor_library.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9e_factor_library.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9e_factor_library.py -q \
  --confcutdir=tests/research_data
```

并保持 `verify_phase9c_factor_evaluation.py` 与 `verify_phase9d_factor_mining.py` 绿。

### Phase 9F Model Platform（9F-1～9F-9 Done）

Registry → Training → Artifact → Evaluation → Approval → Activation → Reproducibility → E2E Hardening；说明：[06_model_platform.md](data/phase9/06_model_platform.md)。

```bash
cd backend_api_python

# 推荐：9F 总验收（串联 9F-1～8 + hardening + golden + 9E）
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9f9_model_platform_e2e.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase9f9_model_platform_e2e.py -q \
  --confcutdir=tests/research_data

# 分阶段（可选）
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9f_model_platform.py
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9f4_qlib_adapter.py
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9f5_model_artifact.py
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9f6_model_evaluation.py
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9f7_model_approval.py
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase9f8_model_reproducibility.py
```

### Phase 8I Architecture Hardening & E2E Acceptance

编排 8A–8H verify + 平面隔离扫描 + FSM/immutability/inject 矩阵 + 单链 E2E + 7E 回归；说明：[09_architecture_hardening_e2e.md](data/phase8/09_architecture_hardening_e2e.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8i_architecture_hardening.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/scan_phase8_plane_isolation.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8i_architecture_hardening.py -q \
  --confcutdir=tests/research_data
```

Phase 8G verify 仍应绿：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8g_strategy_guardrails.py
```

### Phase 8G Strategy Governance & Auto Guardrails（Runtime 保护）

Fake inject + LocalJson 默认；说明：[07_strategy_governance_guardrails.md](data/phase8/07_strategy_governance_guardrails.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8g_strategy_guardrails.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8g_strategy_guardrails.py -q \
  --confcutdir=tests/research_data
```

Phase 8F verify 仍应绿：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8f_strategy_monitoring.py
```

### Phase 8F Strategy Monitoring & Alerting（持续监控）

Fake inject + LocalJson 默认；说明：[06_strategy_monitoring.md](data/phase8/06_strategy_monitoring.md)。

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase8f_strategy_monitoring.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest \
  tests/research_data/test_phase8f_strategy_monitoring.py -q \
  --confcutdir=tests/research_data
```

Phase 8E verify 仍应绿：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8e_performance_feedback.py
```

Phase 8A–8D verify 仍应绿：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8d_promotion_pipeline.py
```

Phase 8A–8C verify 仍应绿：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8a_strategy_registry.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8b_strategy_candidate.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8c_validation_gate.py
```

Phase 7A–7D verify 仍应绿（裸 `LIVE` submit 默认拒）：

```bash
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7a_live_readonly.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7b_shadow_trading.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7c_controlled_live.py
QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase7d_controlled_production.py
```
```

Fake MD + Fake broker 默认；`LIVE` 仍禁；breach 仅 halt 新单，不 auto flatten。

Phase 4 说明：[docs/data/phase4/README.md](data/phase4/README.md)。
Phase 5 说明：[docs/data/phase5/README.md](data/phase5/README.md)。
Phase 6 说明：[docs/data/phase6/README.md](data/phase6/README.md)。

## Level2 因子 D1 Worker

在 `workers/l2-factors-d1`：

```bash
cd workers/l2-factors-d1
npm install
npx wrangler d1 create l2_factors
# 把 database_id 写入 wrangler.toml
npx wrangler d1 migrations apply l2_factors --remote
echo -n '<随机 token>' | npx wrangler secret put WORKER_TOKEN
npx wrangler deploy
```

把 Worker URL 与同一 token 写入 `backend_api_python/.env`：

```
D1_WORKER_URL=https://l2-factors-d1.<account>.workers.dev
D1_WORKER_TOKEN=<随机 token>
```

## Level2

先进入 `backend_api_python`。解释器需要 `pyarrow`。没有本目录 `.venv` 时，脚本会试 `LEVEL2_PYTHON`，再试旁边 level2 仓库里原来的虚拟环境。

| 命令 | 作用 | 改数据 |
| --- | --- | --- |
| `./scripts/run_level2_convert.sh all` | 解压后直接从 CSV 算日频因子并写入 D1，不落明细 Parquet | 会写 D1；达标后删 CSV/.7z |
| `./scripts/run_level2_convert.sh all status` | 查看转换/算因子进程 | 否 |
| `./scripts/run_level2_convert.sh all tail` | 跟踪日志 | 否 |
| `./scripts/run_level2_convert.sh all stop` | 停止进程 | 否 |
| `./scripts/run_level2_convert.sh 20260506 --source 7z` | 只转换这一天为明细 Parquet（单日仍走旧路径） | 会写 staging |
| `./scripts/run_level2_factors.sh all` | 只读 `data/level2_staging/parquet`，从早到晚算尚未写入 D1 的因子并经 Worker 写入 | 会写 D1；本地只留 `level2_staging/factors` 断点标记 |
| `./scripts/run_level2_factors.sh 20260506` | 只算这一天；已写入则跳过 | 同上 |
| `./scripts/run_level2_factors.sh all --force` | 忽略已上传标记，按新规则重算并覆盖写入 D1 | 同上 |
| `./scripts/run_level2_factors.sh 20260506 --force` | 只重算并覆盖这一天 | 同上 |
| `./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922` | 从百度按日下载明细，再算因子并写入 D1，成功后清本地明细；已写入日期跳过 | 会写 D1；本地临时 `level2_parquet` 与断点标记 |
| `./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922 start` | 同上，后台跑 | 同上 |
| `./scripts/run_level2_baidu_factors.sh status` / `tail` / `stop` | 查看、跟踪或停止百度按日流水线 | 否 |
| `QUANTDINGER_SKIP_APP_INIT=1 python scripts/migrate_r2_factors_to_d1.py --dry-run` | 预览 R2/本地日宽表迁移到 D1 的行数与 SQL 句数 | 否 |
| `QUANTDINGER_SKIP_APP_INIT=1 python scripts/migrate_r2_factors_to_d1.py --start 20251009 --end 20260922` | 生成字面量多行 INSERT 的 SQL 分片到 `data/level2_d1_migrate/` | 会写 SQL 分片 |
| `npx wrangler d1 execute l2_factors --remote --file=data/level2_d1_migrate/20251009.sql` | 在 `workers/l2-factors-d1` 下把分片导入 D1 | 会写 D1 |
| `QUANTDINGER_SKIP_APP_INIT=1 python scripts/migrate_r2_factors_to_d1.py --mode worker --date 20251009` | 不经 wrangler，直接经 Worker 批量写入 | 会写 D1 |
| `./scripts/run_level2_factors.sh all --dry-run` | 只打印将要计算的日期 | 否 |
| `./scripts/run_level2_factors.sh all status` | 查看因子进程 | 否 |
| `./scripts/run_level2_upload.sh all` | 把**明细** Parquet 按 `STORAGE_BACKEND` 传到 R2 或百度网盘 | 会写远端 |
| `./scripts/run_level2_upload.sh 20260506` | 只上传这一天的明细 | 会写远端 |
| `python scripts/level2_baidu_oauth.py` | 用授权码换百度 token，写入 `.env` | 会改 `.env` |

`run_level2_convert.sh all` 按日串行：解压 → 从 CSV 算因子 → 写 D1 → 达标删源，默认 8 进程，不写 `level2_staging/parquet` 明细。单日 `convert` 与 `run_level2_factors.sh` 仍可读已有明细 Parquet。都支持 `--workers N`；`--dry-run` 只调度日期。已写入 D1 的日期会跳过。图表/回测读侧以 D1 为真源（需配置 `D1_WORKER_URL` / `D1_WORKER_TOKEN`），并经本地 SQLite（`data/level2_d1_cache.sqlite`）做读缓存；默认约保留三年（`LEVEL2_FACTOR_CACHE_MAX_DAYS=1200`）、总体积上限约 2GB（`LEVEL2_FACTOR_CACHE_MAX_MB=2048`）。日文件只含基础列且发布后删除；云端表是 `l2_factors`，主键 `(trade_date, symbol)`。股票 R2 镜像已废弃（D1 有 `symbol, trade_date` 索引），`--mirror` 为 no-op。某一天因子写入失败时命令返回非 0，并保留 CSV/.7z 便于重试。

百度按日流水线 `run_level2_baidu_factors.sh` 不读 staging 转换产物，直接从网盘拉当日全部股票的三类 Parquet 到 `data/level2_parquet`，下完再算、再写入 D1；成功后删掉当日本地明细，再处理下一日。默认 `--download-workers 1`，按批提交，本地已齐全的股票会跳过。百度请求全局串行；连续连接失败 5 次会熔断休眠 60 秒。当日下载成功率低于 90% 时不算、不上传，已下明细保留便于续跑。令牌过期刷新后写回 `.env`。`--dry-run` 只打印日历日。`--force` 忽略已上传标记。上传失败会停止后续日期，本地明细和日宽表会保留便于重试。若本机长期连不上 `pan.baidu.com`，需要先修网络。

R2→D1 迁移只读按日宽表（`l2_factors/{年}/{年月}/{日}.parquet` 或旧扁平键），不迁 `symbol/`。默认 `--mode wrangler` 用字面量多行 `INSERT OR REPLACE` 尽量塞满每条 SQL（约 90KB），减少写入次数；再用 `wrangler d1 execute --remote --file` 导入。

## 仓库维护

在仓库根目录执行。

| 命令 | 作用 | 改数据 |
| --- | --- | --- |
| `./scripts/generate-secret-key.sh` | 生成 `SECRET_KEY` 并写入 backend `.env` | 会改 `.env` |
| `./scripts/generate-secret-key.ps1` | Windows 上做同样的事 | 会改 `.env` |
| `python scripts/bump_version.py` | 同时改两处 `VERSION` | 会改版本文件 |
| `python scripts/check_version.py` | 核对两处版本一致 | 否 |
| `python scripts/check_docs.py` | 检查文档链接和代码块 | 否 |
| `python scripts/check_mojibake.py` | 检查文件乱码 | 否 |
| `python -m pytest -m "not integration and not stress" --ignore=tests/release_gate -q` | 在 `backend_api_python` 跑常规测试 | 否 |

## 后端脚本

都在 `backend_api_python` 里执行：`python scripts/<名字>.py`。带 `--apply` 的脚本默认只预览，加上后才写库。

| 命令 | 作用 | 改数据 |
| --- | --- | --- |
| `audit_macd_kdj_run.py` | 核对已保存行情上的 MACD/KDJ 信号 | 否 |
| `audit_strategy_runtime.py` | 比较策略运行时版本，不连库、不连交易所 | 否 |
| `backend_quality_check.py` | 检查后端目录结构 | 否 |
| `benchmark_grid_replay.py` | 给网格回放做基准和指纹 | 否 |
| `check_requirements_lock.py` | 核对生产依赖是否都在锁文件里 | 否 |
| `export_openapi.py` | 导出 OpenAPI | 会写指定的输出文件 |
| `exchange_smoke_test.py` | 交易所适配器冒烟；默认只读，下单还要 `--allow-orders` | 默认否 |
| `import_fundamental_snapshots.py` | 从 UTF-8 CSV 导入基本面快照 | 会写库 |
| `generate_market_symbols_seed_sql.py` | 生成标的主数据的 SQL 种子 | 会写 SQL 文件 |
| `refresh_public_universe_snapshots.py` | 从公开源刷新标的宇宙快照 | 会写快照 |
| `sync_market_symbols.py` | 把本地标的主数据同步进 `qd_market_symbols` | 会写库 |
| `validate_strategy_v2_catalog.py` | 生成并校验策略 V2 默认目录 | 会写目录数据 |
| `verify_crypto_kline_matrix.py` | 检查各加密交易所的公开 K 线 | 否 |
| `verify_moex.py` | 检查莫斯科交易所数据源 | 否 |
| `verify_grid_fill_sync.py` | 用契约测试核对网格成交同步；`--live` 才打测试网 | 默认否 |
| `run_calibration.py` | 手动跑一次 AI 校准 | 会写校准结果 |
| `run_reflection_task.py` | 手动跑一次交易反思 | 会写反思结果 |
| `stress_backtest_engine_v2.py` | 跑回测引擎压力场景 | 否 |
| `backfill_zero_trades.py` | 预览价格为 0 的历史成交；`--apply` 才回填 | 加上 `--apply` 会改库 |
| `reconcile_grid_phantom_ledger.py` | 预览网格幽灵账本；`--apply` 才清理 | 加上 `--apply` 会改库 |
| `migrate_canonical_symbols.py` | 预览规范代码合并；`--apply` 才改持仓 | 加上 `--apply` 会改库 |
| `migrate_robot_v2_capital_scaling.py` | 把旧机器人策略源迁到当前资金口径 | 会改库 |
| `backfill_marketplace_strategy_contracts.py` | 给已发布的市场策略补合约元数据 | 会改库 |
| `repair_strategy_source_contracts.py` | 用当前编译器重建策略源元数据 | 会改库 |
| `migrate_r2_factors_to_d1.py` | R2/本地日因子迁 D1（默认生成 wrangler SQL） | 见参数 |
| `convert_blueprints_to_smorest.py` | 把路由从 Flask Blueprint 改成 flask-smorest | 会改源码 |
| `migrate_blueprint_to_smorest.py` | 同上，按文件迁移 | 会改源码 |
| `use_human_blueprint.py` | 把路由改回 HumanBlueprint | 会改源码 |
| `fix_flask_imports.py` | 修正 Blueprint 转换后的 import | 会改源码 |
