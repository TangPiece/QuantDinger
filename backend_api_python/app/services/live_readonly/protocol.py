"""Phase 7A：Live Read-only Domain（真实 Broker 只读；硬禁写单）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

ENGINE_VERSION = "qd_live_readonly@1"

TradingEnvironment = Literal[
    "PAPER",
    "SHADOW",
    "LIVE_READONLY",
    "LIVE_CONTROLLED",
    "LIVE",
]


class LiveReadonlyCapabilities(_ContractModel):
    """Live 只读能力声明：全部写能力为 False。"""

    supports_market_order: bool = False
    supports_limit_order: bool = False
    supports_cancel: bool = False
    supports_replace: bool = False
    supports_fractional: bool = False
    supports_short: bool = False
    supports_margin: bool = False
    supports_websocket: bool = True
    supports_streaming_positions: bool = False
    supports_paper: bool = False
    supports_read_account: bool = True
    supports_read_positions: bool = True
    supports_read_orders: bool = True
    supports_read_executions: bool = True


class LiveReadonlySession(_ContractModel):
    """Live 只读 TradingSession；dataset/model/strategy 生命周期内不可变。"""

    session_id: str
    environment: TradingEnvironment = "LIVE_READONLY"
    account_id: str = ""
    portfolio_id: str = ""
    trading_date: str = ""
    dataset_hash: str = ""
    model_version: str = ""
    strategy_version: str = ""
    status: str = "OPEN"  # OPEN | CLOSED
    engine_version: str = ENGINE_VERSION
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
