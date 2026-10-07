"""Phase 7B：行情 WS 订阅桩（只读；重连 hook）。"""

from __future__ import annotations

from typing import Callable, Optional

from .protocol import MarketEvent


class LiveMdStreamStub:
    """占位 stream：不发起真实 WS；供 runner 挂接重连回调。"""

    def __init__(
        self,
        *,
        on_event: Callable[[MarketEvent], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        self._on_event = on_event
        self._on_reconnect = on_reconnect
        self._subscribed: set[str] = set()
        self._connected = False

    def subscribe(self, symbols: list[str]) -> None:
        """记录订阅标的（stub 不触网）。"""
        for s in symbols:
            self._subscribed.add(str(s).upper())

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def trigger_reconnect(self) -> None:
        """测试/运维 hook：模拟断线重连。"""
        if self._on_reconnect is not None:
            self._on_reconnect()

    def emit(self, event: MarketEvent) -> None:
        if self._on_event is not None:
            self._on_event(event)

    @property
    def subscribed(self) -> frozenset[str]:
        return frozenset(self._subscribed)
