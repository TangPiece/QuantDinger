"""Phase 6B：Portfolio / Position Domain（停在 PositionDelta；无 Broker/OMS）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field, model_validator

from app.services.research_data.contracts import (
    ProductionAccountSummary,
    ProductionPortfolioApplySummary,
    ProductionPortfolioSnapshotSummary,
    ProductionPortfolioSummary,
    ProductionPositionEventRecord,
    ProductionPositionSummary,
    TargetPosition,
    _ContractModel,
)

ENGINE_VERSION = "qd_portfolio_service@1"

PortfolioEnvironment = Literal["PAPER", "SHADOW"]
PortfolioMarket = Literal["CN_A", "HK", "US"]
AccountStatus = Literal["ACTIVE", "PAUSED", "RECONCILIATION_REQUIRED", "CLOSED"]
ApplyMode = Literal["PAPER_FILL", "SHADOW_DRY"]

PositionEventType = Literal[
    "BUY_FILLED",
    "SELL_FILLED",
    "FREEZE",
    "UNFREEZE",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "CORPORATE_ACTION",
    "ADJUSTMENT",
    "MARK_TO_MARKET",
]


class CashBalance(_ContractModel):
    """现金余额：cash = available_cash + frozen_cash。"""

    currency: str = "CNY"
    available_cash: float = 0.0
    frozen_cash: float = 0.0

    @property
    def cash(self) -> float:
        return float(self.available_cash) + float(self.frozen_cash)


class Position(_ContractModel):
    """持仓：quantity = available_quantity + frozen_quantity。"""

    instrument_key: str
    quantity: float = 0.0
    available_quantity: float = 0.0
    frozen_quantity: float = 0.0
    avg_cost: float = 0.0
    market_value: float = 0.0
    currency: str = "CNY"
    as_of: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sync_qty(self) -> Position:
        # 若只给了 available/frozen，回填 quantity；反之拆分到 available
        av = float(self.available_quantity)
        fr = float(self.frozen_quantity)
        qty = float(self.quantity)
        if qty == 0.0 and (av != 0.0 or fr != 0.0):
            object.__setattr__(self, "quantity", av + fr)
        elif abs(qty - (av + fr)) > 1e-9 and fr == 0.0 and av == 0.0:
            object.__setattr__(self, "available_quantity", qty)
        return self


class PnL(_ContractModel):
    """独立 P&L 模型（不塞进 Position 主键）。"""

    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    funding_tax: float = 0.0

    @property
    def total_pnl(self) -> float:
        return (
            float(self.realized_pnl)
            + float(self.unrealized_pnl)
            - float(self.fees)
            - float(self.slippage)
            - float(self.funding_tax)
        )


class Exposure(_ContractModel):
    """三级敞口：instrument / market / portfolio。"""

    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    long_exposure: float = 0.0
    short_exposure: float = 0.0
    instrument_exposure: dict[str, float] = Field(default_factory=dict)
    market_exposure: dict[str, float] = Field(default_factory=dict)
    portfolio_exposure: float = 0.0


class Account(_ContractModel):
    """生产账户视图。"""

    account_id: str
    environment: PortfolioEnvironment = "PAPER"
    market: PortfolioMarket = "CN_A"
    status: AccountStatus = "ACTIVE"
    currency: str = "CNY"
    cash: CashBalance = Field(default_factory=CashBalance)
    market_value: float = 0.0
    equity: float = 0.0
    pnl: PnL = Field(default_factory=PnL)
    exposure: Exposure = Field(default_factory=Exposure)
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def recompute_equity(self) -> Account:
        """统一口径：equity = available + frozen + market_value。"""
        eq = (
            float(self.cash.available_cash)
            + float(self.cash.frozen_cash)
            + float(self.market_value)
        )
        return self.model_copy(update={"equity": eq})


class Portfolio(_ContractModel):
    """账户下的组合（可绑定 runtime）。"""

    portfolio_id: str
    account_id: str
    runtime_id: str = ""
    bundle_hash: str = ""
    status: AccountStatus = "ACTIVE"
    trading_date: str = ""
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PositionEvent(_ContractModel):
    """持仓事件（审计 / 回放）。"""

    event_id: str
    portfolio_id: str
    account_id: str = ""
    event_type: PositionEventType | str
    instrument_key: str = ""
    trading_date: str = ""
    quantity: float = 0.0
    price: float = 0.0
    cash_delta: float = 0.0
    fee: float = 0.0
    idempotency_key: str = ""
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class PositionDelta(_ContractModel):
    """目标仓 vs 当前仓差额（不直接下单）。"""

    instrument_key: str
    current_weight: float = 0.0
    target_weight: float = 0.0
    delta_weight: float = 0.0
    current_quantity: float = 0.0
    target_quantity: float = 0.0
    delta_quantity: float = 0.0
    side: Literal["BUY", "SELL", "FLAT"] = "FLAT"
    notional: float = 0.0


class PositionSnapshot(_ContractModel):
    """持仓快照行。"""

    instrument_key: str
    trading_date: str = ""
    quantity: float = 0.0
    available_quantity: float = 0.0
    frozen_quantity: float = 0.0
    avg_cost: float = 0.0
    market_value: float = 0.0
    weight: float = 0.0
    unrealized_pnl: float = 0.0


class PortfolioSnapshot(_ContractModel):
    """组合周期快照（生产域，独立于回测 ledger）。"""

    snapshot_id: str
    account_id: str
    portfolio_id: str
    trading_date: str = ""
    knowledge_time: Optional[str] = None
    cash: float = 0.0
    available_cash: float = 0.0
    frozen_cash: float = 0.0
    market_value: float = 0.0
    equity: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    fees: float = 0.0
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    turnover: float = 0.0
    runtime_id: str = ""
    bundle_hash: str = ""
    positions: list[PositionSnapshot] = Field(default_factory=list)
    exposure: Exposure = Field(default_factory=Exposure)
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioState(_ContractModel):
    """Reducer 内存态：账户现金 + 持仓 map。"""

    account: Account
    portfolio: Portfolio
    positions: dict[str, Position] = Field(default_factory=dict)
    event_seq: int = 0


class ApplyTargetsResult(_ContractModel):
    """apply_targets 结果；停在 PositionDelta（+ PAPER fill 后的状态）。"""

    apply_id: str
    account_id: str
    portfolio_id: str
    snapshot_id: str = ""
    idempotency_key: str = ""
    trading_date: str = ""
    status: Literal["OK", "SKIPPED_IDEMPOTENT", "FAILED"] = "OK"
    reused: bool = False
    apply_mode: ApplyMode = "PAPER_FILL"
    deltas: list[PositionDelta] = Field(default_factory=list)
    events: list[PositionEvent] = Field(default_factory=list)
    snapshot: Optional[PortfolioSnapshot] = None
    pnl: PnL = Field(default_factory=PnL)
    exposure: Exposure = Field(default_factory=Exposure)
    account: Optional[Account] = None
    positions: list[Position] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "Account",
    "AccountStatus",
    "ApplyMode",
    "ApplyTargetsResult",
    "CashBalance",
    "Exposure",
    "PnL",
    "Portfolio",
    "PortfolioEnvironment",
    "PortfolioMarket",
    "PortfolioSnapshot",
    "PortfolioState",
    "Position",
    "PositionDelta",
    "PositionEvent",
    "PositionEventType",
    "PositionSnapshot",
    "ProductionAccountSummary",
    "ProductionPortfolioApplySummary",
    "ProductionPortfolioSnapshotSummary",
    "ProductionPortfolioSummary",
    "ProductionPositionEventRecord",
    "ProductionPositionSummary",
    "TargetPosition",
]
