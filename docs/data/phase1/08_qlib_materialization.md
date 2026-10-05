# Phase 1C — Qlib Materializer

> **Status:** Phase 1C implemented (DataQuery → Qlib derived cache).
> Qlib Adapter / Factor Lab / Backtest remain out of scope.
>
> **Rule:** R2 Canonical is research fact SSOT; Qlib Cache is always disposable derived artifact.

## 1. Architecture

```text
Dataset (Registry)
      ↓
DataQuery  (market / universe / dataset)
      ↓
Qlib Materializer
      ↓
Local qlib-cache/{materialization_id}/
      ↓
Qlib LocalProvider (minimal readback)
```

Hard constraints:

- Materializer **never** imports Source / PG / R2 SDK / HTTP API
- Only write target: local Qlib cache (+ locks)
- PIT remains in DataQuery; Materializer does not re-query fundamentals

Code: `backend_api_python/app/services/research_data/qlib_materializer/`

## 2. Cache Layout

```text
{QD_RESEARCH_CACHE_DIR|~/.quantdinger/cache}/qlib-cache/
├── {materialization_id}/
│   ├── calendars/day.txt
│   ├── instruments/all.txt
│   ├── features/{sh600000}/close.day.bin
│   ├── metadata/
│   │   ├── instrument_mapping.parquet
│   │   └── feature_mapping.json
│   └── manifest.json
└── locks/{materialization_id}.lock
```

Atomic build: `{id}.building/` → validate → rename → `READY`.

## 3. Dataset → Qlib Mapping

| Domain | Qlib |
| --- | --- |
| `DataQuery.market` rows | `features/{inst}/{field}.day.bin`（`<f4`，**首元为 calendar start_index**，其后为值） |
| Unique `trading_date` | `calendars/day.txt` |
| Universe snapshot members | `instruments/all.txt`（**小写** `sh600000\\tstart\\tend`） |
| `DatasetDefinition.features` | `metadata/feature_mapping.json` |

> Qlib `FileFeatureStorage` 要求 `.day.bin = hstack([start_index, values])`。仅写 values 会导致 `D.features` 空表。

## 4. Instrument Mapping

QuantDinger `InstrumentKey` (actual): `CNStock:600000`

Qlib instrument（展示/mapping）：`SH600000` / `SZ000001`  
落盘 `instruments/all.txt` 与 `features/`：**小写** `sh600000` / `sz000001`。

Rule: A-share code starting with `6` → `SH`, else `SZ`.

Mapping table: `metadata/instrument_mapping.parquet`
(`instrument_key`, `qlib_instrument`, `exchange`, `symbol`, `valid_from`, `valid_to`)

## 5. Calendar Mapping

Calendar is derived from **DataQuery.market** trading dates for the Dataset universe/window
(`DataQuery.trading_calendar` is a thin helper). Never use Qlib’s default calendar as SSOT.

## 6. Feature Mapping

Phase 1C allows only: `open/high/low/close/volume/amount/vwap`.

Example:

```json
{
  "close": {
    "source": "canonical.market.close",
    "qlib_feature": "$close",
    "qlib_field": "close"
  }
}
```

Unsupported expressions (e.g. `Ref($close,-1)`, Alpha158) → `UnsupportedFeatureError`.

## 7. Price Policy

Materializer reads `dataset.price_policy` and calls
`DataQuery.market(..., price_policy=...)`.

- `none` → raw Canonical prices
- `post` → 1B post-adjustment via CA
- `pre` → still not implemented (fails in DataQuery)

Different `price_policy` changes `dataset_hash` ⇒ different `materialization_id`.

## 8. Manifest

`manifest.json` includes: dataset_code/version/hash, snapshot_id, schema_version,
price_policy, processor, materializer_version, materialization_id, qlib_version,
calendar stats, instruments count, features, checksum, status=READY.

## 9. Cache Identity

```text
MATERIALIZER_VERSION = "qlib_materializer@1"
materialization_id = sha256(dataset_hash + "|" + MATERIALIZER_VERSION)
```

- `dataset_hash`: Domain semantics (1B; materializer_version remains `"none"` in hash inputs)
- `qlib_version`: recorded in manifest only (not folded into dataset_hash)

## 10. Determinism

Same `dataset_hash` + `materializer_version` ⇒ same logical calendar / instruments /
feature alignment / checksum tree (parquet binary equality not required).

Idempotent: READY + valid checksum ⇒ cache hit.

## 11. Validation

真读回验收（装有 pyqlib 时强制）：

1. Cache 可被 `qlib.init` + `D.*` 读取  
2. Calendar：`D.calendar` == DataQuery `trading_calendar`  
3. Instruments：小写 tab 三段式，且 `D.list_instruments` 一致  
4. DataHandlerLP / OHLCV 面板非空  
5. `feature_mapping.json`：`$close` ↔ `canonical.market.close`  
6. DataQuery vs `D.features` 数值一致（`atol=1e-8`, `rtol=1e-6`）；NaN 不漂成 0  

有 qlib 时 `D.features` 空结果视为失败（不再静默成功）。

CLI:

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python scripts/materialize_qlib_dataset.py \
  --dataset-ref cn_stock_daily@v1 \
  --local-root /tmp/qd_canonical \
  --registry-root /tmp/qd_registry \
  --wipe

QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \
  python scripts/verify_qlib_cache_readback.py
```

Tests: `python -m pytest tests/research_data/test_qlib_*.py -q`

## 12. Known Limitations

```text
Qlib Adapter 尚未实现
Model / Signal / Strategy Adapter 尚未实现
Factor Lab / Alpha158 尚未实现
Processor Runtime 尚未实现
Backtest 尚未实现
pre 复权尚未实现
非 CNStock market 映射尚未实现
不做 Qlib 性能优化 / 全 A 十年 benchmark
pyqlib 依赖链很重（mlflow/jupyter 等）；未安装时 Materializer 仍写出兼容目录，
并以文件系统层校验 calendar/instruments；安装 pyqlib 后走 D.calendar / D.features 读回
```

### Architecture conflicts resolved

| Topic | Resolution |
| --- | --- |
| Package path | Under `research_data/qlib_materializer/` (not new `app/research/`) |
| Cache dir name | `qlib-cache/{materialization_id}` (docs prefix + task identity) |
| InstrumentKey | Keep `CNStock:code` → map to `SH/SZ` |

## Stop

Phase 1C stops here. Do not auto-start Phase 2 Adapter.
