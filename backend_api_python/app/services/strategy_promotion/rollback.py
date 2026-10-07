"""Phase 8D：RollbackRecord + 7E rollback 包装。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.strategy_registry.identity import strategy_id_from_code

from .bridge_to_runtime import open_rollback_session
from .identity import new_rollback_id
from .protocol import RollbackRecord


class PromotionRollbackError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_rollback(
    *,
    strategy_code: str,
    to_version: str,
    reason: str,
    operator: str,
    governance: Any | None = None,
    from_version: str = "",
) -> RollbackRecord:
    """PAUSE + 回切 previous stable version（新 session）。"""
    code = str(strategy_code).strip()
    target = str(to_version).strip()
    if not code or not target:
        raise PromotionRollbackError("strategy_code and to_version required")
    active = from_version
    if governance is not None:
        sid = strategy_id_from_code(code)
        lc = getattr(governance, "_lifecycle", {}).get(sid)
        if lc is not None:
            active = active or str(getattr(lc, "active_version", "") or "")
        if hasattr(governance, "rollback_strategy"):
            governance.rollback_strategy(sid, to_version=target)
    sess = open_rollback_session(strategy_code=code, to_version=target)
    return RollbackRecord(
        rollback_id=new_rollback_id(),
        strategy_code=code,
        from_version=active or target,
        to_version=target,
        reason=str(reason or ""),
        operator=str(operator or ""),
        session_id=sess,
        created_at=_now(),
    )


__all__ = ["PromotionRollbackError", "execute_rollback"]
