# QuantDinger 命令

在仓库根目录执行，除非某一节写明要先进入 `backend_api_python`。Level2 明细和因子都在 `backend_api_python/data/`，不进 git。

| 目录 | 内容 |
| --- | --- |
| `data/level2_raw` | 原始 `.7z` 和已解压的 CSV |
| `data/level2_staging/parquet` | 转换后的三类明细 |
| `data/level2_staging/factors` | 批量算出的日频因子，一天一个文件 |
| `data/level2_parquet` | 图表临时下载的明细，算完会删 |
| `data/level2_factors` | 图表和回测读取的日频因子 |

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

## Level2

先进入 `backend_api_python`。解释器需要 `pyarrow`。没有本目录 `.venv` 时，脚本会试 `LEVEL2_PYTHON`，再试旁边 level2 仓库里原来的虚拟环境。

| 命令 | 作用 | 改数据 |
| --- | --- | --- |
| `./scripts/run_level2_convert.sh all` | 解压并转换成 Parquet，不算因子 | 会写 staging，达标后删源 |
| `./scripts/run_level2_convert.sh all status` | 查看转换进程 | 否 |
| `./scripts/run_level2_convert.sh all tail` | 跟踪转换日志 | 否 |
| `./scripts/run_level2_convert.sh all stop` | 停止转换 | 否 |
| `./scripts/run_level2_convert.sh 20260506 --source 7z` | 只转换这一天 | 会写 staging |
| `./scripts/run_level2_factors.sh all` | 只读 `data/level2_staging/parquet`，从早到晚算尚未上传的因子并上传 R2 | 会写 `level2_staging/factors` 和 R2 |
| `./scripts/run_level2_factors.sh 20260506` | 只算这一天；已经上传过则跳过 | 同上 |
| `./scripts/run_level2_factors.sh all --force` | 忽略已上传标记，按新规则重算全部日文件并覆盖 R2，成功后再上传每只股票的镜像 | 会写 `level2_staging/factors` 和 R2 |
| `./scripts/run_level2_factors.sh 20260506 --force` | 只重算并覆盖这一天的宽表，不重建股票镜像 | 同上 |
| `./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922` | 从百度按日下载明细：日内先并行下完全市场，再算因子并上传 R2，成功后清本地明细再进下一日；已上传日期跳过 | 会写 `level2_parquet`（临时）、`level2_staging/factors` 和 R2 |
| `./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922 start` | 同上，后台跑 | 同上 |
| `./scripts/run_level2_baidu_factors.sh status` / `tail` / `stop` | 查看、跟踪或停止百度按日流水线 | 否 |
| `QUANTDINGER_SKIP_APP_INIT=1 python -m app.services.level2_factors.symbol_mirror` | 把本地按日因子收成每只股票一个文件并上传 | 会写 R2 的 `l2_factors/symbol/` |
| `./scripts/run_level2_factors.sh all --dry-run` | 只打印将要计算的日期 | 否 |
| `./scripts/run_level2_factors.sh all status` | 查看因子进程 | 否 |
| `./scripts/run_level2_upload.sh all` | 把明细 Parquet 按 `STORAGE_BACKEND` 传到 R2 或百度网盘 | 会写远端 |
| `./scripts/run_level2_upload.sh 20260506` | 只上传这一天的明细 | 会写远端 |
| `python scripts/level2_baidu_oauth.py` | 用授权码换百度 token，写入 `.env` | 会改 `.env` |

转换和因子分开跑，都支持 `--workers N`。转换的 `--dry-run` 只调度日期。因子默认同一天 8 个进程，用 `./scripts/run_level2_factors.sh all` 手动计算；它的 `--dry-run` 只打印日期。已完成且已上传的日期会跳过。要按当前规则整批重算并覆盖上传，用 `./scripts/run_level2_factors.sh all --force`：日文件只含基础列，对象键仍是 `l2_factors/{年}/{年月}/{YYYYMMDD}.parquet`，全部成功后再上传 `l2_factors/symbol/{代码}.parquet`。单日 `--force` 只覆盖那一天。只补股票镜像、不重算时，仍可单独跑 `symbol_mirror`。读 R2 时若没有年月路径，仍会试以前的 `l2_factors/{YYYYMMDD}.parquet`。某一天因子上传失败时，因子命令返回非 0，并且不会重建股票镜像。

百度按日流水线 `run_level2_baidu_factors.sh` 不读 staging 转换产物，直接从网盘拉当日全部股票的三类 Parquet 到 `data/level2_parquet`，下完再算、再上传；上传成功后删掉当日本地明细，再处理下一日。`--dry-run` 只打印日历日。`--force` 忽略已上传标记。`--mirror` 在区间全部成功后再重建股票镜像。上传失败会停止后续日期，本地明细和日宽表会保留便于重试。

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
| `run_reflection_task.py` | 手动跑一次交易反思 | 会写反思记录 |
| `stress_backtest_engine_v2.py` | 跑回测引擎压力场景 | 否 |
| `backfill_zero_trades.py` | 预览价格为 0 的历史成交；`--apply` 才回填 | 加上 `--apply` 会改库 |
| `reconcile_grid_phantom_ledger.py` | 预览网格幽灵账本；`--apply` 才清理 | 加上 `--apply` 会改库 |
| `migrate_canonical_symbols.py` | 预览规范代码合并；`--apply` 才改持仓 | 加上 `--apply` 会改库 |
| `migrate_robot_v2_capital_scaling.py` | 把旧机器人策略源迁到当前资金口径 | 会改库 |
| `backfill_marketplace_strategy_contracts.py` | 给已发布的市场策略补合约元数据 | 会改库 |
| `repair_strategy_source_contracts.py` | 用当前编译器重建策略源元数据 | 会改库 |
| `convert_blueprints_to_smorest.py` | 把路由从 Flask Blueprint 改成 flask-smorest | 会改源码 |
| `migrate_blueprint_to_smorest.py` | 同上，按文件迁移 | 会改源码 |
| `use_human_blueprint.py` | 把路由改回 HumanBlueprint | 会改源码 |
| `fix_flask_imports.py` | 修正 Blueprint 转换后的 import | 会改源码 |
