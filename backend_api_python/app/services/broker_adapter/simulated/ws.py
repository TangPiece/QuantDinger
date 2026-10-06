"""Fake WebSocket：推送 execution events；支持 disconnect/reconnect/resubscribe。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..events import NormalizedBrokerEvent, make_normalized_event


class SimulatedWebSocket:
    """进程内 WS：队列 + 断线缓冲。"""

    def __init__(self, *, broker_id: str = "simulated") -> None:
        self.broker_id = broker_id
        self.connected = False
        self.subscribed = False
        self._queue: list[NormalizedBrokerEvent] = []
        self._buffer: list[NormalizedBrokerEvent] = []  # 断线期间积压
        self._disconnect_after_n: Optional[int] = None
        self._pushed = 0

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False
        self.subscribed = False

    def subscribe_executions(self) -> None:
        if not self.connected:
            raise RuntimeError("ws not connected")
        self.subscribed = True
        # 重订阅后把缓冲灌入队列
        if self._buffer:
            self._queue.extend(self._buffer)
            self._buffer.clear()

    def configure_disconnect_after(self, n: int) -> None:
        self._disconnect_after_n = int(n)

    def push(self, event: NormalizedBrokerEvent) -> None:
        """推送事件；断线时缓冲。"""
        if not self.connected or not self.subscribed:
            self._buffer.append(event)
            return
        self._queue.append(event)
        self._pushed += 1
        if (
            self._disconnect_after_n is not None
            and self._pushed >= self._disconnect_after_n
        ):
            self.disconnect()
            self._disconnect_after_n = None

    def push_raw(
        self,
        *,
        broker_execution_id: str,
        event_type: str,
        client_order_id: str = "",
        broker_order_id: str = "",
        order_id: str = "",
        quantity: float = 0.0,
        price: float = 0.0,
        filled_quantity: float = 0.0,
        remaining_quantity: float = 0.0,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> NormalizedBrokerEvent:
        ev = make_normalized_event(
            broker_id=self.broker_id,
            broker_execution_id=broker_execution_id,
            event_type=event_type,
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            order_id=order_id,
            quantity=quantity,
            price=price,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            message=message,
            payload=payload,
        )
        self.push(ev)
        return ev

    def drain(self) -> list[NormalizedBrokerEvent]:
        out = list(self._queue)
        self._queue.clear()
        return out

    def reconnect_and_resubscribe(self) -> None:
        self.connect()
        self.subscribe_executions()
