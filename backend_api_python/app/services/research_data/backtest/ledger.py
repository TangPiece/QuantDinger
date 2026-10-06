"""回测账本：Trade → Position → Portfolio → Equity（可审计链路）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from app.services.research_data.contracts import _ContractModel


class TradeRecord(_ContractModel):
    """单笔成交记录；用于 Qlib vs Production 差异分析。"""

    trade_id: str
    instrument_key: str
    side: Literal["BUY", "SELL"]
    quantity: float
    requested_price: Optional[float] = None
    executed_price: Optional[float] = None
    signal_time: Optional[datetime] = None
    order_time: Optional[datetime] = None
    execution_time: Optional[datetime] = None
    commission: float = 0.0
    tax: float = 0.0
    slippage: float = 0.0
    status: Literal["FILLED", "PARTIAL", "REJECTED", "CANCELLED"] = "FILLED"
    signal_id: Optional[str] = None
    reject_reason: Optional[str] = None


class PositionSnapshot(_ContractModel):
    """某日持仓快照。"""

    instrument_key: str
    trading_date: str
    quantity: float = 0.0
    average_cost: Optional[float] = None
    market_value: Optional[float] = None
    weight: Optional[float] = None
    unrealized_pnl: Optional[float] = None


class PortfolioSnapshot(_ContractModel):
    """组合层面快照。"""

    trading_date: str
    cash: float = 0.0
    total_value: float = 0.0
    positions: list[PositionSnapshot] = []
    # Phase 3D 账本审计（可选）
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_cost: float = 0.0


class EquityPoint(_ContractModel):
    """权益曲线点。"""

    trading_date: str
    timestamp: Optional[datetime] = None
    equity: float
    drawdown: Optional[float] = None
