# Trading Rules

## TradingRule contract

| Field | A-share example |
| --- | --- |
| `lot_size` | 100 shares |
| `tick_size` | 0.01 CNY |
| `t_plus` | 1 (T+1 settlement) |
| `limit_up_down` | true |
| `limit_up_down_pct` | 0.10 |
| `short_allowed` | false |
| `fractional_shares` | false |
| `market_calendar_id` | `CN_SSE_SZSE` |
| `suspension_mode` | skip / hold / fail |

Production backtest (3D) must enforce these strictly. Qlib research (3B) may use `research_qlib_relaxed()` with simplified rules but still emit `TradeRecord` in the same schema.

## Relation to `instrument_rules.py`

Crypto live rules live in [`instrument_rules.py`](../../backend_api_python/app/services/instrument_rules.py) with immutable snapshots for historical backtests. Phase 3A defines the **research contract**; mapping exchange snapshots into `TradingRule` is a 3D concern.
