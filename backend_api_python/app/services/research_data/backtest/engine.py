"""BacktestEngine 协议（Phase 3B/3D 实现；3A 无实现类）。"""

from __future__ import annotations

from typing import Protocol

from .request import BacktestRequest
from .result import BacktestResult


class BacktestEngine(Protocol):
    """与引擎无关的回测入口；禁止在此 import qlib。"""

    def run(self, request: BacktestRequest) -> BacktestResult:
        """执行回测并返回 Domain BacktestResult。"""
        ...
