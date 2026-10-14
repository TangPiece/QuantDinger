# fund_cn_basic@v1 — A-share fundamental factors

## Storage contract

```text
Source (AKShare + disclosure calendar)
  → Local staging: data/fundamental_staging/fund_cn/
  → R2 Canonical: qd/canonical/fundamental/pit/exchange=CN/year=YYYY/
  → R2 Factor:    qd/factor/daily/factor_set=fund_cn_basic@v1/...
D1 qd_research: fund_cn_* definitions / jobs / datasets / period_status (metadata only)
```

Do **not** write financial values into Level2 `l2_factors` hot table.

## Sources

| Data | Adapter | Notes |
| --- | --- | --- |
| Statements | `AkshareStatementAdapter` → `stock_{balance,profit,cash_flow}_sheet_by_report_em` | English columns (`OPERATE_INCOME`, `PARENT_NETPROFIT`, `TOTAL_PARENT_EQUITY`, `NETCASH_OPERATE` …); each field has an ordered candidate list, first non-null wins |
| Disclosure calendar | same adapter, `NOTICE_DATE` / `UPDATE_DATE` | Combined snapshot waits for every contributing sheet; latest-only restatements become visible from `UPDATE_DATE` |
| Total shares | `CninfoShareCapitalAdapter` → `stock_share_change_cninfo` | `总股本` in 万股 → shares; `变动日期` effective, `公告日期` announced |

Field conventions: `revenue` = 营业收入 (fallback 营业总收入); `net_profit_parent` / `shareholder_equity` are parent-only; `gross_profit` = revenue − 营业成本; `operating_expenses` = 销售 + 管理 + 研发 + 财务费用（四项必须齐全，除非源端直接给出总额）; `free_cash_flow` = OCF − |capex| on YTD cumulatives; `interest_bearing_debt` = 短期借款 + 长期借款 + 应付债券（三项必须全部显式存在，包括显式 0）。

**Latest-only source limitation:** Eastmoney does not provide the superseded values. When `UPDATE_DATE > NOTICE_DATE`, the adapter marks the current snapshot as `revision=1` and delays it to `UPDATE_DATE`; it does not reconstruct revision 0. This is conservative (no look-ahead) but leaves the interval before the update empty unless a curated revision history is supplied.

## PIT / statement revisions

- Statement snapshots are keyed by `(instrument, report_period, revision)`.
- Announce calendar joins on the **same revision** (no last-write-wins backfill onto older revisions); duplicate announces for the same `(period, revision)` keep the earliest `available_time`.
- If multiple revisions of one period share exactly the same `available_time`, only the highest revision is emitted because lower revisions had no independent visible interval.
- Date-only disclosures (pure date or naive midnight) become visible at **D 16:00 UTC (Beijing D+1 00:00)**, so the D close never uses an evening release. Daily panels use KT = trade day 07:00 UTC (Beijing 15:00).
- Each observation is evaluated against the state visible at its own `available_time`: per (field, fiscal quarter) the latest visible revision.
- Daily as-of lookups (`compute._build_asof_index`, `DataQuery.fundamental`) select the **latest report period**, then latest revision, then latest `available_time`. A late restatement of an older period never replaces a newer visible period.
- Report factors are not forward-filled more than `DEFAULT_MAX_STALENESS_DAYS` (548) after the report period end.

## Cumulative vs single-quarter

Income / cashflow fields from A-share reports are treated as **YTD cumulative**. Before YoY and TTM:

- Single quarter is **re-differenced at query time** from visible cumulatives: Q1 = cum; Qn = cum(Qn) − cum(Qn−1). A Q3 restatement published after Q4 therefore changes the Q4 single quarter used from then on. Missing prior quarter → `None`. `field__sq` columns from `to_single_quarter` are display-only.
- Balance-sheet fields stay point-in-time
- TTM = 4 **consecutive** single quarters ending at the current period (FY may use the year cumulative); any gap → `None`. First three quarters of history have no TTM.
- YoY growth factors use **single-quarter** series: `(cur − lag) / |lag|`; a negative base represents loss narrowing/widening rather than ordinary profit growth. Earnings volatility needs 8 consecutive quarters.
- `cash_dividend` is treated as **period occurrence** (not YTD); TTM sums reported periods in the 4-quarter window without differencing

### time_basis

| Family | time_basis | Notes |
| --- | --- | --- |
| ROE / ROA / margins / expense / OCF ratios / capex / turnover / AR & inventory to revenue / accruals | `ttm` | TTM numerator over point-in-time balance; comparable across Q1/H1/Q3/FY disclosure windows |
| YoY growth (flows) | `sq` | Single-quarter after YTD→SQ |
| PE / PS / PCF / FCF yield / ROIC numerator | `ttm` | Trailing four quarters |
| Balance levels / debt ratios / asset & equity YoY | `point_in_time` | Snapshot as of report period |

ROE and ROA in v1 use end-of-period equity/assets, not average balances. The factor named `roic` is explicitly an approximation: pre-tax operating profit divided by end-of-period equity plus interest-bearing debt; it is not NOPAT-based standard ROIC.

## Valuation

`mcap = close × total_shares`:

- `close` must be the **unadjusted** close (Canonical bars store raw prices).
- `total_shares` is **total share capital (总股本)** from share-change events, usable from `max(effective_date, announce_time)`; among usable events the latest effective date wins. This keeps PE/PB continuous through 送转 / 增发 / 回购注销.
- Without events for an issuer, the report-period `shares_outstanding` PIT metric is used and a warning is logged (stale after capital changes).
- Valuation factors require a non-empty market panel.
- Negative earnings/OCF produce negative raw PE/PCF values. They are retained for v1 compatibility and must not be interpreted as ordinary positive valuation multiples.
- Invalid/non-finite values and denominators with absolute value at or below `1e-12` produce `None`.

## Factor kinds

| Kind | Examples | Compute |
| --- | --- | --- |
| report | ROE, margins, YoY, leverage | PIT metric → daily forward-fill (`available_time <= trade day`) |
| valuation | PE_TTM, PB, PS_TTM, PCF | daily `close * shares` / PIT TTM fundamentals |

Units: stored as **decimal ratios** (`0.15` = 15%), `unit=ratio`.

Factors tagged `applicability=non_financial` use industrial-company statement semantics. Until bank/insurance-specific mappings exist, their missing fields must remain missing rather than being interpreted as zero.

## Gates

Each factor tracks `RAW_OK` / `COMPUTE_OK` / `PIT_OK`. Only all-green + enabled factors are default `PIT_SAFE` for Factor Lab backtests. `promote` sets gates + `enabled=True` + `PIT_SAFE`. `run_pipeline` registers PIT_SAFE factors only when staging coverage passes (`require_coverage=True` by default).

## Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python -m app.services.research_data.fund_cn catalog
QUANTDINGER_SKIP_APP_INIT=1 python -m app.services.research_data.fund_cn coverage
QUANTDINGER_SKIP_APP_INIT=1 python -m app.services.research_data.fund_cn compute \
  --instruments CNStock:000001 --dates 2024-04-01 \
  --market-file /path/to/unadjusted_daily.parquet
QUANTDINGER_SKIP_APP_INIT=1 python -m app.services.research_data.fund_cn register
QUANTDINGER_SKIP_APP_INIT=1 ./scripts/run_fund_cn.sh catalog
```

`stage` fetches statements, NOTICE_DATE calendar and cninfo share-change events (`share_capital/share_capital.parquet` in staging).
`compute` requires a CSV/Parquet market file with `instrument_key`, `trading_date`, and unadjusted `close`. `register` enforces staging coverage by default; `--allow-uncovered` is diagnostic-only.

Offline / tests: call `orchestrator.run_pipeline(..., statement_rows=..., announce_rows=..., share_capital_rows=..., market=...)`.

Qlib materializer remains OHLCV-only; consume fundamentals via `DataQuery.fundamental` / Factor Lab `PIT_SAFE`.
