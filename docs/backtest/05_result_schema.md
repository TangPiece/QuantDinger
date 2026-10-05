# Result Schema & Ledgers

## Audit chain

```text
Signal / TargetPosition
        ↓
Order (3B+)
        ↓
TradeRecord
        ↓
PositionSnapshot
        ↓
PortfolioSnapshot
        ↓
EquityPoint
        ↓
BacktestMetrics
```

## TradeRecord

Required for explaining engine diffs (e.g. CAGR 31% vs 24%):

- Times: `signal_time`, `order_time`, `execution_time`
- Prices: `requested_price`, `executed_price`
- Costs: `commission`, `tax`, `slippage`
- `status`, `reject_reason` (limit up, suspension, lot size, …)

## BacktestMetrics (names only in 3A)

- Return: `total_return`, `annualized_return`
- Risk: `volatility`, `sharpe`, `sortino`, `max_drawdown`, `calmar`
- Activity: `turnover`, `win_rate`, `profit_factor`

Values are populated in 3B+; contract ensures both engines log the same keys.
