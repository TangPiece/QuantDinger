"""Phase 8D：PromotionLock — 同 strategy 仅一个 IN_PROGRESS Run。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from .protocol import PromotionRunStatus


class PromotionLockError(RuntimeError):
    """并发晋升冲突。"""


class PromotionLock:
    """基于 D1/LocalJson Run 索引的轻量锁。"""

    def __init__(self, registry: ResearchRegistry) -> None:
        self._registry = registry

    def _in_progress_for(self, strategy_code: str) -> list[Any]:
        try:
            rows = self._registry.list_strategy_promotion_runs(strategy_code=strategy_code)
        except Exception:
            return []
        return [r for r in rows if str(getattr(r, "status", "")) == "IN_PROGRESS"]

    def acquire(self, strategy_code: str, *, pipeline_run_id: str) -> None:
        """若已有其他 IN_PROGRESS Run 则拒绝。"""
        code = str(strategy_code).strip()
        pid = str(pipeline_run_id).strip()
        for row in self._in_progress_for(code):
            existing_id = str(getattr(row, "pipeline_run_id", ""))
            if existing_id and existing_id != pid:
                raise PromotionLockError(
                    f"strategy {code!r} already has IN_PROGRESS run {existing_id!r}"
                )

    def assert_not_blocked(self, strategy_code: str) -> None:
        if self._in_progress_for(str(strategy_code).strip()):
            raise PromotionLockError("promotion lock held")


__all__ = ["PromotionLock", "PromotionLockError"]
