"""Execution 去重：unique(broker_id, broker_execution_id)。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .hash import dedup_key


class ExecutionDeduper:
    """内存 + Registry 双重去重。"""

    def __init__(
        self,
        *,
        try_record: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._seen: set[str] = set()
        self._try_record = try_record

    def seen(self, broker_id: str, broker_execution_id: str) -> bool:
        key = dedup_key(broker_id, broker_execution_id)
        return key in self._seen

    def try_accept(self, broker_id: str, broker_execution_id: str) -> bool:
        """首次 True；重复 False。"""
        if not broker_execution_id:
            return True
        key = dedup_key(broker_id, broker_execution_id)
        if key in self._seen:
            return False
        if self._try_record is not None:
            ok = self._try_record(broker_id, broker_execution_id)
            if not ok:
                self._seen.add(key)
                return False
        self._seen.add(key)
        return True
