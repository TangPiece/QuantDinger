"""Phase 8G：8D Rollback lineage 包装（不改 Immutable Version 内容）。"""

from __future__ import annotations

from typing import Any

from app.services.strategy_promotion.rollback import execute_rollback


def run_promotion_rollback(
    promotion: Any | None,
    *,
    strategy_code: str,
    to_version: str,
    reason: str,
    operator: str,
    governance: Any | None = None,
    from_version: str = "",
) -> Any:
    """调用 8D execute_rollback + 7E rollback_strategy。"""
    return execute_rollback(
        strategy_code=strategy_code,
        to_version=to_version,
        reason=reason,
        operator=operator,
        governance=governance,
        from_version=from_version,
    )


__all__ = ["run_promotion_rollback"]
