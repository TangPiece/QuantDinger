"""简单组合构建：Signal → TargetPosition（无复杂资金约束）。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from app.services.research_data.contracts import Signal, TargetPosition
from app.services.research_data.hashing import canonical_json


class PortfolioBuilder(Protocol):
    """组合构建协议。"""

    @property
    def portfolio_code(self) -> str: ...

    def portfolio_digest(self) -> str: ...

    def build(
        self,
        signals: list[Signal],
        *,
        portfolio_id: str,
    ) -> tuple[list[TargetPosition], float]:
        """返回 (positions, cash_weight)；股票权重之和 + cash_weight == 1。"""
        ...


@dataclass(frozen=True)
class EqualWeightPortfolio:
    """对 LONG 信号等权；剩余记 cash_weight。可选只取截面 Top-N LONG。"""

    top_n: int | None = None
    max_gross: float = 1.0
    code: str = "equal_weight"
    version: str = "1"

    @property
    def portfolio_code(self) -> str:
        return f"{self.code}@{self.version}"

    def portfolio_digest(self) -> str:
        payload = {
            "code": self.code,
            "version": self.version,
            "top_n": self.top_n,
            "max_gross": self.max_gross,
        }
        return hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()

    def build(
        self,
        signals: list[Signal],
        *,
        portfolio_id: str,
    ) -> tuple[list[TargetPosition], float]:
        if self.max_gross <= 0 or self.max_gross > 1:
            raise ValueError("max_gross must be in (0, 1]")
        # 按交易日分组
        by_day: dict[str, list[Signal]] = {}
        for s in signals:
            by_day.setdefault(s.trading_date, []).append(s)

        positions: list[TargetPosition] = []
        # 多日时各日独立等权；cash 取末日（metadata 用末日 cash）
        cash_weight = 1.0
        for day in sorted(by_day.keys()):
            day_sigs = by_day[day]
            longs = [s for s in day_sigs if s.direction == "LONG"]
            longs.sort(key=lambda s: (-float(s.score), s.instrument_key))
            if self.top_n is not None:
                longs = longs[: self.top_n]
            n = len(longs)
            if n == 0:
                # 当日无 LONG：不产出仓位，也不改写全局 cash_weight
                continue
            w = float(self.max_gross) / float(n)
            cash_weight = 1.0 - float(self.max_gross)
            strategy_version = longs[0].strategy_version
            dataset_hash = longs[0].dataset_hash
            for s in longs:
                positions.append(
                    TargetPosition(
                        instrument_key=s.instrument_key,
                        trading_date=day,
                        portfolio_id=portfolio_id,
                        strategy_version=strategy_version,
                        dataset_hash=dataset_hash,
                        timestamp=s.signal_time,
                        target_weight=w,
                        signal_id=s.signal_id,
                    )
                )
                # 回写策略可选 target_weight（Signal 可变副本留给 runner）
        return positions, cash_weight
