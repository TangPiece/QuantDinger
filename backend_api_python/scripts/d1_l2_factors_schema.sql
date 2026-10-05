-- Level2 日频基础因子表（与 workers/l2-factors-d1/migrations/0001_l2_factors.sql 一致）
CREATE TABLE IF NOT EXISTS l2_factors (
  trade_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  l2_spread REAL,
  l2_depth_bid REAL,
  l2_depth_ask REAL,
  l2_obi REAL,
  l2_ofi REAL,
  l2_order_ratio REAL,
  l2_active_net_buy REAL,
  l2_big_net_inflow_rate REAL,
  l2_cancel_ratio REAL,
  l2_auction_amount REAL,
  l2_auction_imbalance REAL,
  l2_ret_overnight REAL,
  l2_ret_open_30 REAL,
  l2_ret_tail_30 REAL,
  l2_ret_intraday REAL,
  l2_rv REAL,
  l2_rskew REAL,
  PRIMARY KEY (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_l2_factors_symbol_date
  ON l2_factors (symbol, trade_date);
