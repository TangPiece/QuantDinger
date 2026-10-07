"""Phase 8G：禁止 pause/throttle 时无授权跨策略 capital 再分配。"""

from __future__ import annotations

from typing import Any, Mapping


class CapitalReallocationForbiddenError(RuntimeError):
    """违反 Capital 锁：不得自动转移释放额度。"""


def assert_no_capital_reallocation(
    *,
    action: str,
    context: Mapping[str, Any] | None = None,
) -> None:
    ctx = dict(context or {})
    if ctx.get("reallocate_capital"):
        raise CapitalReallocationForbiddenError("capital reallocation forbidden in guardrails")
    if ctx.get("target_strategy_code") and str(action).upper() in ("PAUSE", "THROTTLE", "STOP"):
        raise CapitalReallocationForbiddenError(
            "cross-strategy capital move forbidden on guardrail action"
        )


__all__ = ["CapitalReallocationForbiddenError", "assert_no_capital_reallocation"]
