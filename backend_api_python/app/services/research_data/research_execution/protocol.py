"""Phase 5C：研究侧执行仿真 Domain（成本 / 约束 / 归因）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

EXECUTION_PROFILE_VERSION = "qd_research_execution@1"

RealismMode = Literal["GROSS", "NET"]
MarketRuleId = Literal["CN_A", "HK", "US"]
PriceAdjustment = Literal["none"]


class ExecutionPricePolicy(_ContractModel):
    """执行价语义：与研究复权价分离；v1 强制原始可交易价。"""

    adjustment: PriceAdjustment = "none"
    reference_note: str = "raw_ohlcv_for_fills"


class ExecutionProfile(_ContractModel):
    """挂到 BacktestSpec 的执行画像指纹。"""

    realism: RealismMode = "GROSS"
    market_rule: MarketRuleId = "CN_A"
    cost_enabled: bool = False
    execution_price_adjustment: PriceAdjustment = "none"
    execution_profile_version: str = EXECUTION_PROFILE_VERSION
    # 覆盖预设时写入规范化 JSON（进 hash）
    cost_policy_json: dict[str, Any] = Field(default_factory=dict)
    trading_rule_json: dict[str, Any] = Field(default_factory=dict)


class DailyCostRow(_ContractModel):
    """日成本汇总行。"""

    trading_date: date
    commission: float = 0.0
    stamp_tax: float = 0.0
    transfer_fee: float = 0.0
    slippage: float = 0.0
    total_cost: float = 0.0
    n_fills: int = 0
    n_rejects: int = 0


class FillRow(_ContractModel):
    """成交/拒单明细行。"""

    trading_date: date
    trade_id: str
    instrument_key: str
    side: str
    quantity: float = 0.0
    executed_price: Optional[float] = None
    commission: float = 0.0
    tax: float = 0.0
    slippage: float = 0.0
    status: str = "FILLED"
    reject_reason: Optional[str] = None


class AttributionBreakdown(_ContractModel):
    """Gross → Net 拖累拆解。"""

    commission_drag: float = 0.0
    stamp_tax_drag: float = 0.0
    slippage_drag: float = 0.0
    transfer_fee_drag: float = 0.0
    unfilled_drag: float = 0.0
    other: float = 0.0


class AttributionReport(_ContractModel):
    """双轨归因：解释为何净收益低于毛收益。"""

    gross_total_return: Optional[float] = None
    net_total_return: Optional[float] = None
    delta_return: Optional[float] = None
    breakdown: AttributionBreakdown = Field(default_factory=AttributionBreakdown)
    initial_nav: float = 1.0
    gross_final_nav: Optional[float] = None
    net_final_nav: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "EXECUTION_PROFILE_VERSION",
    "AttributionBreakdown",
    "AttributionReport",
    "DailyCostRow",
    "ExecutionPricePolicy",
    "ExecutionProfile",
    "FillRow",
    "MarketRuleId",
    "RealismMode",
]
