"""Phase 7B：Live Market Data 契约（Strategy 不依赖券商 SDK 类型）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_live_md@1"


class _MdModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Quote(_MdModel):
    """最新报价快照。"""

    symbol: str
    exchange: str = "US"
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[float] = None
    event_time: str = ""
    received_time: str = ""
    source: str = "fake"
    event_id: str = ""
    sequence: Optional[int] = None


class Bar(_MdModel):
    """K 线 bar。"""

    symbol: str
    exchange: str = "US"
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    vwap: Optional[float] = None
    event_time: str = ""
    received_time: str = ""
    source: str = "fake"
    event_id: str = ""
    timeframe: str = "1Min"


class MarketEvent(_MdModel):
    """统一行情事件（quote 或 bar）。"""

    kind: Literal["quote", "bar"]
    quote: Optional[Quote] = None
    bar: Optional[Bar] = None
    quality_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveMdSession(_MdModel):
    """行情会话：锁定 dataset/model/strategy 版本。"""

    session_id: str
    feed_id: str = "default"
    account_id: str = ""
    dataset_hash: str = ""
    model_version: str = ""
    strategy_version: str = ""
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    opened_at: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)
