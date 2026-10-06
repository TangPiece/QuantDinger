"""回测策略子契约：执行 / 价格 / 费用 / 交易规则（与具体引擎无关）。"""

from __future__ import annotations

from typing import Literal, Optional

from app.services.research_data.contracts import _ContractModel


class ExecutionPolicy(_ContractModel):
    """信号产生与成交时序；Production 须严格，Qlib Research 可简化。"""

    # 信号锚点：如 close_of_signal_day / explicit_signal_time
    signal_time_rule: Literal[
        "close_of_signal_day",
        "open_of_signal_day",
        "explicit",
    ] = "close_of_signal_day"
    # 相对信号日的执行延迟：T+0 / T+1 / calendar_days:N
    execution_delay: str = "T+1"
    execution_price: Literal[
        "open",
        "close",
        "vwap",
        "limit_ref",
        "mid",
    ] = "open"
    execution_mode: Literal["market", "limit", "participation"] = "market"
    participation_rate: Optional[float] = None
    timezone: str = "Asia/Shanghai"


class BacktestMarketPricePolicy(_ContractModel):
    """回测成交价与复权语义（区别于 DataQuery Dataset PricePolicy）。"""

    adjustment: Literal["none", "pre", "post"] = "none"
    return_type: Literal["price", "total"] = "price"
    reference_price: Literal["open", "close", "vwap", "adj_close"] = "close"
    corporate_action_mode: Literal["ignore", "split_only", "full"] = "split_only"


class CostPolicy(_ContractModel):
    """费用与滑点；Phase 3A 仅定义，3C 实现。"""

    commission_rate: float = 0.0
    stamp_tax_rate: float = 0.0
    transfer_fee_rate: float = 0.0
    slippage_bps: float = 0.0
    minimum_commission: float = 0.0
    currency: str = "CNY"


class TradingRule(_ContractModel):
    """市场微观结构规则；3C ExecutionSimulator / Production 3D 执行。"""

    lot_size: int = 100
    tick_size: float = 0.01
    t_plus: int = 1
    limit_up_down: bool = True
    limit_up_down_pct: Optional[float] = 0.1
    short_allowed: bool = False
    fractional_shares: bool = False
    market_calendar_id: str = "CN_SSE_SZSE"
    suspension_mode: Literal["skip", "hold", "fail"] = "skip"
    # floor：向下取整到 lot_size，零头 rejected；reject：非整手整单拒绝
    lot_rounding: Literal["floor", "reject"] = "floor"
    # True 时买入受现金约束（不足则部分/拒绝）
    enforce_cash: bool = True
