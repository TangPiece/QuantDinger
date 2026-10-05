# Price & Cost Policy

## Two price layers

| Layer | Type | Used for |
| --- | --- | --- |
| Dataset / DataQuery | `PricePolicy` in [`contracts.py`](../../backend_api_python/app/services/research_data/contracts.py) | Canonical OHLCV read, `dataset_hash` |
| Backtest | `BacktestMarketPricePolicy` | Fill pricing, corporate actions in simulation |

Both engines must accept the **same** `BacktestMarketPricePolicy` on `BacktestRequest`.

### BacktestMarketPricePolicy

- `adjustment`: none / pre / post
- `return_type`: price / total
- `reference_price`: open / close / vwap / adj_close
- `corporate_action_mode`: ignore / split_only / full

## CostPolicy (defined, not fully implemented until 3C)

| Field | Typical CN equity |
| --- | --- |
| `commission_rate` | Broker commission |
| `stamp_tax_rate` | Sell-side stamp tax |
| `transfer_fee_rate` | Exchange transfer |
| `slippage_bps` | Basis points slippage model |
| `minimum_commission` | Min fee per order |
| `currency` | CNY / USD / … |

Phase 3A stores rates only; no PnL impact yet.
