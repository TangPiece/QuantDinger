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

验证 Qlib Cache 真读回（Calendar / Instruments / D.features / DataHandler / DataQuery 一致性）：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_qlib_cache_readback.py
```

本地单测：`cd workers/qd-research-d1 && npm test`；`cd backend_api_python && python -m pytest tests/research_data -q`。

Phase 1B 验收报告：[docs/data/phase1/07_phase1b_validation.md](data/phase1/07_phase1b_validation.md)。
Phase 1C 物化说明：[docs/data/phase1/08_qlib_materialization.md](data/phase1/08_qlib_materialization.md)。

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
