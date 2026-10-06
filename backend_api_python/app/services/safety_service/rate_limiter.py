"""订单速率滑动窗口（进程内；严重超限可触发 Strategy HALT）。"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque


class OrderRateLimiter:
    """max_orders_per_second / per_minute 检查。"""

    def __init__(self) -> None:
        self._events: dict[str, Deque[float]] = defaultdict(deque)

    def _key(self, account_id: str, strategy_id: str = "") -> str:
        return f"{account_id}|{strategy_id or '_'}"

    def record(self, account_id: str, *, strategy_id: str = "") -> None:
        now = time.monotonic()
        q = self._events[self._key(account_id, strategy_id)]
        q.append(now)
        # 丢弃 >60s 的
        while q and now - q[0] > 60.0:
            q.popleft()

    def counts(
        self, account_id: str, *, strategy_id: str = ""
    ) -> tuple[int, int]:
        """返回 (per_second, per_minute)。"""
        now = time.monotonic()
        q = self._events[self._key(account_id, strategy_id)]
        while q and now - q[0] > 60.0:
            q.popleft()
        per_min = len(q)
        per_sec = sum(1 for t in q if now - t <= 1.0)
        return per_sec, per_min

    def check(
        self,
        account_id: str,
        *,
        strategy_id: str = "",
        max_per_second: float = 10.0,
        max_per_minute: float = 100.0,
    ) -> tuple[bool, str, float]:
        """返回 (ok, reason, trigger_value)。"""
        per_sec, per_min = self.counts(account_id, strategy_id=strategy_id)
        if per_sec > max_per_second:
            return False, f"orders/sec {per_sec}>{max_per_second}", float(per_sec)
        if per_min > max_per_minute:
            return False, f"orders/min {per_min}>{max_per_minute}", float(per_min)
        return True, "", 0.0
