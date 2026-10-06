"""对账游标：EXECUTION / ORDER / SNAPSHOT_TIME。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .protocol import CursorType, ReconciliationCursor


class CursorStore:
    """读写 reconciliation_cursor（Registry/Repository）。"""

    def __init__(self, repository: Any = None) -> None:
        self._repo = repository
        self._mem: dict[str, ReconciliationCursor] = {}

    def _key(self, account_id: str, broker_id: str, cursor_type: str) -> str:
        return f"{account_id}|{broker_id}|{cursor_type}"

    def get(
        self,
        account_id: str,
        *,
        broker_id: str = "",
        cursor_type: CursorType = "EXECUTION",
    ) -> ReconciliationCursor:
        if self._repo is not None:
            try:
                return self._repo.get_cursor(
                    account_id, broker_id=broker_id, cursor_type=cursor_type
                )
            except KeyError:
                pass
        k = self._key(account_id, broker_id, cursor_type)
        return self._mem.get(k) or ReconciliationCursor(
            account_id=account_id,
            broker_id=broker_id,
            cursor_type=cursor_type,
            cursor_value="",
        )

    def set(
        self,
        account_id: str,
        *,
        broker_id: str = "",
        cursor_type: CursorType = "EXECUTION",
        cursor_value: str = "",
    ) -> ReconciliationCursor:
        cur = ReconciliationCursor(
            account_id=account_id,
            broker_id=broker_id,
            cursor_type=cursor_type,
            cursor_value=cursor_value,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._mem[self._key(account_id, broker_id, cursor_type)] = cur
        if self._repo is not None:
            self._repo.set_cursor(cur)
        return cur
