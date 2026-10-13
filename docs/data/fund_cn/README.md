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
| Disclosure calendar | same adapter, `NOTICE_DATE` (earliest across the three sheets) | Default when no explicit announce adapter is passed |
| Total shares | `CninfoShareCapitalAdapter` → `stock_share_change_cninfo` | `总股本` in 万股 → shares; `变动日期` effective, `公告日期` announced |

Field conventions: `revenue` = 营业收入 (fallback 营业总收入); `net_profit_parent` / `shareholder_equity` are parent-only; `gross_profit` = revenue − 营业成本; `operating_expenses` = 销售 + 管理 + 研发 + 财务费用; `free_cash_flow` = OCF − |capex| on YTD cumulatives; `interest_bearing_debt` = 短期借款 + 长期借款 + 应付债券, 0 when a balance sheet exists but all three lines are blank.

**Known look-ahead limitation:** Eastmoney serves only the latest version of each period. When `UPDATE_DATE > NOTICE_DATE` the restated numbers carry the original disclosure date. Use a curated restatement calendar (revision > 0 announce rows) where this matters.

## PIT / statement revisions

- Statement snapshots are keyed by `(instrument, report_period, revision)`.
- Announce calendar joins on the **same revision** (no last-write-wins backfill onto older revisions); duplicate announces for the same `(period, revision)` keep the earliest `available_time`.
- Date-only disclosures (pure date or naive midnight) become visible at **D 16:00 UTC (Beijing D+1 00:00)**, so the D close never uses an evening release. Daily panels use KT = trade day 07:00 UTC (Beijing 15:00).
- Each observation is evaluated against the state visible at its own `available_time`: per (field, fiscal quarter) the latest visible revision.
- Daily as-of lookups (`compute._build_asof_index`, `DataQuery.fundamental`) select the **latest report period**, then latest revision, then latest `available_time`. A late restatement of an older period never replaces a newer visible period.
- Report factors are not forward-filled more than `DEFAULT_MAX_STALENESS_DAYS` (548) after the report period end.

## Cumulative vs single-quarter

Income / cashflow fields from A-share reports are treated as **YTD cumulative**. Before YoY and TTM:

- Single quarter is **re-differenced at query time** from visible cumulatives: Q1 = cum; Qn = cum(Qn) − cum(Qn−1). A Q3 restatement published after Q4 therefore changes the Q4 single quarter used from then on. Missing prior quarter → `None`. `field__sq` columns from `to_single_quarter` are display-only.
- Balance-sheet fields stay point-in-time
- TTM = 4 **consecutive** single quarters ending at the current period (FY may use the year cumulative); any gap → `None`. First three quarters of history have no TTM.
- YoY growth factors use **single-quarter** series: `(cur − lag) / |lag|`; earnings volatility needs 8 consecutive quarters.
- `cash_dividend` is treated as **period occurrence** (not YTD); TTM sums reported periods in the 4-quarter window without differencing

### time_basis

| Family | time_basis | Notes |
| --- | --- | --- |
| ROE / ROA / margins / expense / OCF ratios / capex / turnover / AR & inventory to revenue / accruals | `ttm` | TTM numerator over point-in-time balance; comparable across Q1/H1/Q3/FY disclosure windows |
| YoY growth (flows) | `sq` | Single-quarter after YTD→SQ |
| PE / PS / PCF / FCF yield / ROIC numerator | `ttm` | Trailing four quarters |
| Balance levels / debt ratios / asset & equity YoY | `point_in_time` | Snapshot as of report period |

## Valuation

`mcap = close × total_shares`:

- `close` must be the **unadjusted** close (Canonical bars store raw prices).
- `total_shares` is **total share capital (总股本)** from share-change events, usable from `max(effective_date, announce_time)`; among usable events the latest effective date wins. This keeps PE/PB continuous through 送转 / 增发 / 回购注销.
- Without events for an issuer, the report-period `shares_outstanding` PIT metric is used and a warning is logged (stale after capital changes).
- Valuation factors require a non-empty market panel.

## Factor kinds

| Kind | Examples | Compute |
| --- | --- | --- |
| report | ROE, margins, YoY, leverage | PIT metric → daily forward-fill (`available_time <= trade day`) |
| valuation | PE_TTM, PB, PS_TTM, PCF | daily `close * shares` / PIT TTM fundamentals |

Units: stored as **decimal ratios** (`0.15` = 15%), `unit=ratio`.

## Gates

Each factor tracks `RAW_OK` / `COMPUTE_OK` / `PIT_OK`. Only all-green + enabled factors are default `PIT_SAFE` for Factor Lab backtests. `promote` sets gates + `enabled=True` + `PIT_SAFE`. `run_pipeline` registers PIT_SAFE factors only when staging coverage passes (`require_coverage=True` by default).

## Commands

```bash
cd backend_api_python
QUANTDINGER_SKIP_APP_INIT=1 python -m app.services.research_data.fund_cn catalog
QUANTDINGER_SKIP_APP_INIT=1 python -m app.services.research_data.fund_cn coverage
QUANTDINGER_SKIP_APP_INIT=1 ./scripts/run_fund_cn.sh catalog
```

`stage` fetches statements, NOTICE_DATE calendar and cninfo share-change events (`share_capital/share_capital.parquet` in staging).

Offline / tests: call `orchestrator.run_pipeline(..., statement_rows=..., announce_rows=..., share_capital_rows=..., market=...)`.

Qlib materializer remains OHLCV-only; consume fundamentals via `DataQuery.fundamental` / Factor Lab `PIT_SAFE`.
