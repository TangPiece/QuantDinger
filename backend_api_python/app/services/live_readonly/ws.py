"""Phase 7A：Live WebSocket 只订阅 stub（不下单）。"""

from __future__ import annotations

from typing import Any, Callable, Optional


class LiveReadonlyWebSocketStub:
    """占位：仅记录 subscribe 意图，不发送 trade 指令。"""

    def __init__(self) -> None:
        self._connected = False
        self._handlers: list[Callable[[dict[str, Any]], None]] = []

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def subscribe_trade_updates(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """注册 trade_updates 回调；7A 不建立真实 WS。"""
        self._handlers.append(handler)

    @property
    def connected(self) -> bool:
        return self._connected
