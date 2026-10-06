"""OMS 查询面：is_blocked / decide。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .evaluate import evaluate
from .protocol import SafetyContext, TradingGateDecision


class SafetyGate:
    """供 OMS 注入的闸门；Fail-Closed。"""

    def __init__(self, service: Any) -> None:
        self._svc = service

    def is_blocked(self, account_id: str, *, strategy_id: str = "") -> bool:
        """兼容 6F TradingGate.is_blocked；账户/策略/全局任一阻断即 True。"""
        try:
            d = self._svc.decide(
                account_id,
                intent=None,
                strategy_id=strategy_id,
            )
            return str(d.decision).upper() != "ALLOW"
        except Exception:
            return True  # Fail-Closed

    def decide(
        self,
        account_id: str,
        intent: Any = None,
        *,
        strategy_id: str = "",
        prices: Mapping[str, float] | None = None,
        context: SafetyContext | None = None,
    ) -> TradingGateDecision:
        return self._svc.decide(
            account_id,
            intent=intent,
            strategy_id=strategy_id,
            prices=prices,
            context=context,
        )
