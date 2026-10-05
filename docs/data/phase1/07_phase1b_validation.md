# Phase 1B — Golden Dataset & DataQuery Validation

> **Status:** Phase 1B complete (fixture Golden `cn_stock_daily@v1` + DuckDB Repository + tests).
> Qlib Adapter / Materializer / Factor Lab / Backtest remain out of scope.

## 1. Dataset

| Field | Value |
| --- | --- |
| `dataset_code` | `cn_stock_daily` |
| `dataset_version` | `v1` |
| `dataset_ref` | `cn_stock_daily@v1` |
| `snapshot_id` | `snap_cn_stock_daily_v1_2024.03`（示例固定 id；CLI 可改） |
| `status` | `validated`（Registry 文本列 / Local `_registry_status`） |
| `dataset_hash` | `bf728933c3dba59e5abc09b069d2dd66db4e058dd388caab0720ac88af8b4bb1` |

`dataset_hash` 输入（已锁定）：`dataset_definition` + `dataset_version` + `snapshot_id` + `schema_version` + `processor_version` + `materializer_version=none` + `price_policy`。

复现示例：

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/build_golden_dataset.py \
  --start 2024-01-01 --end 2024-03-31 \
  --universe-version 2024.03 \
  --snapshot-id snap_cn_stock_daily_v1_2024.03
```

## 2. 数据范围

| Field | Value |
| --- | --- |
| market | CN equity daily OHLCV（Canonical raw） |
| universe | CSI300（fixture membership snapshot） |
| frequency | `1d` |
| requested start/end | `2020-01-01` .. `2025-12-31`（CLI 默认）；示例跑 `2024-01-01` .. `2024-03-31` |
| actual range (fixture 示例) | `2024-01-01` .. `2024-03-01`（按月首日合成点） |
| instrument_count (示例) | 3（`CNStock:000001/000002/600000`） |
| market row_count (示例) | 9 |
| PIT | `ROE`（`available_time` 必填） |
| corporate_action | 合成 `split_ratio=1.1` @ `2024-06-01`（支撑 `post`） |
| trading_status | 空分区占位（无可靠源时不伪造） |

**规则：** Source 覆盖不足时截断到可用区间，不伪造行情。

## 3. Storage

### 数据流

```text
QuantDinger Source / fixture
        ↓ ingest only
Canonical Writer (parquet)
        ↓
R2 qd/canonical/...  或  LocalCanonicalStore
        ↓ local cache (CachingCanonicalStore)
CanonicalRepository (DuckDB read_parquet)
        ↓
DataQuery
        ↓
cn_stock_daily@v1
```

### R2 / 逻辑路径（示例 fixture）

```text
qd/canonical/market/daily/exchange=CN/year=2024/month=01/part-000.parquet
qd/canonical/market/daily/exchange=CN/year=2024/month=02/part-000.parquet
qd/canonical/market/daily/exchange=CN/year=2024/month=03/part-000.parquet
qd/canonical/fundamental/pit/exchange=CN/year=2024/part-000.parquet
qd/canonical/corporate_action/exchange=CN/year=2024/part-000.parquet
qd/canonical/trading_status/exchange=CN/year=2024/month=01/part-000.parquet
qd/canonical/universe/code=CSI300/version=2024.03/part-000.parquet
qd/snapshot/{snapshot_id}/manifest.json
```

| Aspect | Value |
| --- | --- |
| Parquet schema | `market_bar_daily@1` / `pit_fundamental@1` / `corporate_action@1` / `trading_status@1` / `universe_membership_snapshot@1` |
| checksum | per-object sha256（Registry `data_version` + snapshot items） |
| CI 默认 | LocalCanonicalStore（不依赖外网） |
| 生产可选 | `--use-r2` → `CachingCanonicalStore(R2, Local)` |

## 4. PIT

| Check | Result |
| --- | --- |
| `available_time <= knowledge_time` | pass（`test_pit_leakage.py`） |
| revision 取最新 | pass |
| future rows leak | pass（无泄漏） |

## 5. Universe

| Check | Result |
| --- | --- |
| as-of 仅读 Canonical snapshot | pass |
| 重写新 version 不影响旧 version | pass |
| monkeypatch PG members 后 snapshot 不变 | pass（`test_universe_pg_mutation_isolation.py`） |

## 6. DataQuery

| Layer | Implementation |
| --- | --- |
| API | `dataset(dataset_ref)` / `market` / `fundamental` / `universe` / `corporate_actions` / `trading_status`（对齐 `05_contracts.md`） |
| Canonical Repository | `canonical_repository.py`：物化本地路径 + DuckDB `read_parquet` |
| DuckDB | OHLCV 列齐全；可 `ORDER BY instrument_key, trading_date` |
| Price policy | `none` = raw；`post` = 用 CA `split_ratio` 后复权；`pre` = `NotImplementedError` |
| Cache stats | `CachingCanonicalStore.hits/misses` + `invalidate` |

硬约束：`DataQuery` / `CanonicalRepository` **永不** import `CNStockDataSource` / market HTTP；仅 `ingest/*` 可调 Source。

## 7. Tests

命令：`cd backend_api_python && python -m pytest tests/research_data -q`

| Test | Result |
| --- | --- |
| `test_pit_leakage.py` | pass |
| `test_dataquery_no_live_api.py` | pass |
| `test_schema_validation.py` | pass |
| `test_dataset_hash.py`（含 Case D processor / Case E schema） | pass |
| `test_universe_snapshot_stability.py` | pass |
| `test_price_policy_consistency.py` | pass |
| `test_dataquery_boundary.py` | pass |
| `test_price_policy.py`（none≠post） | pass |
| `test_canonical_determinism.py` | pass |
| `test_cache_hit_miss.py` | pass |
| `test_universe_pg_mutation_isolation.py` | pass |
| `test_duckdb_market_query.py` | pass |
| `test_golden_dataset_end_to_end.py` | pass |

**Suite:** 26 passed（Phase 1B 实现后）。

## 8. Known limitations

尚未实现 / 明确不做：

```text
Qlib Materializer
Qlib Adapter
Qlib Cache / Alpha158
Factor Lab
Backtest
Kafka / Flink / K8s
改 l2_factors / Level2 ingest / 前端
PricePolicy.adjustment = pre
完整分红现金再投资 total return
真实全量 CSI300 2020–2025 外网灌库（CI 用 fixture；`--from-source` 可选）
trading_status 真实源（当前空分区）
```

### 架构冲突（相对任务书原文，按已批准 1A 契约执行）

| 点 | 任务书 | 已批准 / 1B 处理 |
| --- | --- | --- |
| `dataset` | `dataset(code, version)` | 保留 `dataset(dataset_ref)` = `code@version` |
| `feature` | `feature(code, version)` | 保留 1A 签名；1B 不扩 Factor Lab |
| price 命名 | `raw` / `adjusted` | 映射：raw=`none`，adjusted=`post` |
| DuckDB 位置 | `R2→DuckDB→DataQuery` | `DataQuery→CanonicalRepository→(Store/DuckDB)` |

## Stop

Phase 1B 到此停止。不自动开启 Phase 1C（Qlib Materializer）。
