"""Phase 8G：6G Safety Stop NEW ORDERS（无 flatten）。"""

from __future__ import annotations

from typing import Any

from app.services.trading_governance.kill import halt_strategy


class SafetyBridgeError(RuntimeError):
    pass


def safety_stop_new_orders(
    safety: Any | None,
    *,
    account_id: str,
    strategy_id: str,
    reason: str = "",
) -> None:
    """EMERGENCY 路径：BLOCK_NEW_ORDER / halt_strategy。"""
    if safety is None:
        return
    halt_strategy(safety, account_id=account_id, strategy_id=strategy_id, reason=reason)


__all__ = ["SafetyBridgeError", "safety_stop_new_orders"]
