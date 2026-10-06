"""执行算法：v1 仅 MARKET；VWAP/TWAP 留接口。"""

from __future__ import annotations

from typing import Protocol


class ExecutionAlgorithm(Protocol):
    """未来 Level2 / TWAP / VWAP 挂载点。"""

    name: str

    def is_supported(self) -> bool: ...


class MarketAlgorithm:
    """默认市价算法（走 OHLCV ExecutionSimulator）。"""

    name = "MARKET"

    def is_supported(self) -> bool:
        return True


class VwapAlgorithm:
    """占位：5C v1 未实装。"""

    name = "VWAP"

    def is_supported(self) -> bool:
        return False


class TwapAlgorithm:
    """占位：5C v1 未实装。"""

    name = "TWAP"

    def is_supported(self) -> bool:
        return False


def resolve_algorithm(name: str) -> ExecutionAlgorithm:
    """解析算法；不支持则返回占位对象。"""
    key = (name or "MARKET").upper()
    mapping: dict[str, ExecutionAlgorithm] = {
        "MARKET": MarketAlgorithm(),
        "VWAP": VwapAlgorithm(),
        "TWAP": TwapAlgorithm(),
    }
    return mapping.get(key, MarketAlgorithm())
