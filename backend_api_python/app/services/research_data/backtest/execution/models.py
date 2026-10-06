"""Phase 3C 执行层模型与拒单 reason 常量。"""

from __future__ import annotations

from typing import Literal, Optional

from app.services.research_data.contracts import _ContractModel


# 标准化拒单 / 部分成交原因（写入 ExecutionDecision.reason / TradeRecord.reject_reason）
REASON_T_PLUS = "T_PLUS"
REASON_EXECUTION_DELAY = "EXECUTION_DELAY"
REASON_LOT_SIZE_FLOOR = "LOT_SIZE_FLOOR"
REASON_LOT_SIZE_REJECT = "LOT_SIZE_REJECT"
REASON_LIMIT_UP = "LIMIT_UP"
REASON_LIMIT_DOWN = "LIMIT_DOWN"
REASON_SUSPENDED = "SUSPENDED"
REASON_SHORT_NOT_ALLOWED = "SHORT_NOT_ALLOWED"
REASON_INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
REASON_NO_PRICE = "NO_PRICE"
REASON_HOLD = "HOLD"
REASON_OK = "OK"


class EligibilityFlags(_ContractModel):
    """单标的当日可交易性快照。"""

    is_suspended: bool = False
    is_limit_up: bool = False
    is_limit_down: bool = False
    buy_ok: bool = True
    sell_ok: bool = True


class MarketBar(_ContractModel):
    """日频行情输入（最小字段，供 eligibility / 定价）。"""

    instrument_key: str
    trading_date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    vwap: Optional[float] = None
    volume: Optional[float] = None
    is_suspended: bool = False
    is_limit_up: bool = False
    is_limit_down: bool = False
    upper_limit: Optional[float] = None
    lower_limit: Optional[float] = None


class CostBreakdown(_ContractModel):
    """单笔成交费用拆账。"""

    commission: float = 0.0
    stamp_tax: float = 0.0
    transfer_fee: float = 0.0
    slippage: float = 0.0
    other_fee: float = 0.0
    total_cost: float = 0.0
    gross_value: float = 0.0
    # BUY: cash_out = gross + total；SELL: cash_in = gross - total
    net_cash_delta: float = 0.0


class ExecutionDecision(_ContractModel):
    """是否可执行及数量拆分（审计友好）。"""

    instrument_key: str
    side: Literal["BUY", "SELL"]
    executable: bool
    reason: str = REASON_OK
    requested_quantity: float = 0.0
    executable_quantity: float = 0.0
    rejected_quantity: float = 0.0
    eligibility: EligibilityFlags = EligibilityFlags()
    fill_price: Optional[float] = None
