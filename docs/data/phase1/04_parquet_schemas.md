# 04 — Parquet Schemas

## Type policy

Do **not** force every numeric column to Float64.

| Semantic | Arrow / Parquet type |
| --- | --- |
| Prices, factors, amounts, VWAP, ratios | `float64` |
| Volume | `float64` for CN daily Phase 1 (vendor mixes units); document if later switched to `int64` |
| Revision / rank / lot-related ints | `int32` |
| Flags | `bool` |
| Calendar dates | `date32` |
| Event / publish / available times | `timestamp[us, tz]` (store UTC) |
| Keys, codes, versions, sources | `utf8` / string |

Compression: ZSTD recommended. Row group sizing left to implementers; prefer fewer large files per partition.

## `market_bar_daily`

Path: `qd/canonical/market/daily/exchange=.../year=.../month=.../`

| Column | Type | Notes |
| --- | --- | --- |
| `instrument_key` | string | e.g. `CNStock:000001` |
| `trading_date` | date32 | Exchange trading calendar date |
| `open` | float64 | **Raw** unadjusted |
| `high` | float64 | Raw |
| `low` | float64 | Raw |
| `close` | float64 | Raw |
| `volume` | float64 | |
| `amount` | float64 | |
| `vwap` | float64 | Optional; null if unavailable |
| `data_version` | string | Logical version id |

Rules:

- Never overwrite raw OHLC with adjusted prices in Canonical.
- Adjustment factors live in corporate-action tables; `price_policy` applied in Query/Materializer.
- Partition columns `exchange`, `year`, `month` may be physical dirs only (not duplicated as required columns), but including `exchange` as a column is allowed for self-describing files.

## `corporate_action`

Path: `qd/canonical/corporate_action/exchange=.../year=.../`

| Column | Type |
| --- | --- |
| `instrument_key` | string |
| `effective_date` | date32 |
| `action_type` | string |
| `cash_dividend` | float64 |
| `split_ratio` | float64 |
| `rights_ratio` | float64 |
| `rights_price` | float64 |
| `currency` | string |
| `source` | string |
| `source_version` | string |
| `data_version` | string |

`action_type` examples: `DIVIDEND`, `SPLIT`, `RIGHTS`, `BONUS`.

## `trading_status`

Path: `qd/canonical/trading_status/exchange=.../year=.../month=.../`

| Column | Type |
| --- | --- |
| `instrument_key` | string |
| `trading_date` | date32 |
| `status` | string |
| `is_suspended` | bool |
| `is_limit_up` | bool |
| `is_limit_down` | bool |
| `upper_limit` | float64 |
| `lower_limit` | float64 |
| `data_version` | string |

## `pit_fundamental`

Path: `qd/canonical/fundamental/pit/exchange=.../year=.../`

| Column | Type | Notes |
| --- | --- | --- |
| `instrument_key` | string | |
| `metric_code` | string | e.g. `ROE`, `PE` |
| `report_period_start` | date32 | nullable |
| `report_period_end` | date32 | |
| `fiscal_year` | int32 | nullable |
| `fiscal_quarter` | int32 | nullable |
| `publish_time` | timestamp[us, tz] | Vendor/market publish |
| `available_time` | timestamp[us, tz] | System obtainable time — **PIT key** |
| `value` | float64 | |
| `unit` | string | |
| `currency` | string | |
| `revision` | int32 | |
| `is_restatement` | bool | |
| `source` | string | |
| `source_record_id` | string | |
| `data_version` | string | |

PIT read algorithm (must match Contract):

```text
filter available_time <= knowledge_time
order by available_time DESC, revision DESC
limit 1 per (instrument_key, metric_code) [and report period policy]
```

## `universe_membership_snapshot`

Path: `qd/canonical/universe/code={CODE}/version={VERSION}/`

**Required for research.** Immutable membership intervals.

| Column | Type | Notes |
| --- | --- | --- |
| `universe_code` | string | |
| `universe_version` | string | Directory version; denormalized for safety |
| `instrument_key` | string | |
| `valid_from` | date32 | Inclusive |
| `valid_to` | date32 | Nullable = open-ended at snapshot time |
| `weight` | float64 | Nullable |
| `member_rank` | int32 | Nullable |
| `source_version` | string | |
| `snapshot_id` | string | Links to D1/R2 snapshot |

As-of membership:

```text
valid_from <= as_of_date
AND (valid_to IS NULL OR valid_to >= as_of_date)
```

## Factor schemas

### Wide — stable factor sets

Path: `qd/factor/daily/factor_set={code}@{version}/...`

| Column | Type |
| --- | --- |
| `instrument_key` | string |
| `trading_date` | date32 |
| `{FACTOR_A}` | float64 |
| `{FACTOR_B}` | float64 |
| ... | float64 |
| `data_version` | string |

Use for versioned sets such as `alpha158@1.0.0`. Column set is frozen per `factor_set@version`.

### Long — dynamic / AI factors

Path: same prefix pattern with a dedicated `factor_set` (e.g. `rdagent_batch_20261005@1`)

| Column | Type |
| --- | --- |
| `instrument_key` | string |
| `trading_date` | date32 |
| `factor_code` | string |
| `factor_version` | string |
| `value` | float64 |
| `data_version` | string |

Rules:

- Stable Factor Set → Wide
- Dynamic / AI / exploding cardinality → Long or isolated Factor Set
- Never append unbounded columns onto a shared mega wide table

## Snapshot / dataset JSON (not Parquet)

See [03_r2_layout.md](03_r2_layout.md) for `manifest.json` and `def.json` shapes.

## Validation hooks (for later CI)

Market:

- `high >= low`, `high >= open`, `high >= close`, `low <= open`, `low <= close`
- `volume >= 0`, `amount >= 0`

PIT:

- `available_time` present
- `revision >= 0`

Universe:

- `valid_to` null or `valid_to >= valid_from`
