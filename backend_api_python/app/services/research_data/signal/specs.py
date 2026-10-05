"""SignalRunSpec：策略 + 组合 + 时间策略名。"""

from __future__ import annotations

from dataclasses import dataclass

from .portfolio import EqualWeightPortfolio, PortfolioBuilder
from .strategies import SignalStrategy, TopKStrategy


@dataclass
class SignalRunSpec:
    """一次 Signal 管线运行规格。"""

    strategy: SignalStrategy
    portfolio: PortfolioBuilder
    # 文档化时间约定名（实现见 timeutil.resolve_signal_times）
    time_policy: str = "cn_close_next_calendar_open"
    persist: bool = True

    @classmethod
    def default_topk(cls, k: int = 3) -> "SignalRunSpec":
        """内置默认：TopK + 等权。"""
        return cls(
            strategy=TopKStrategy(k=k),
            portfolio=EqualWeightPortfolio(),
        )
