"""Outbox：enqueue / drain（与 Order 写入同事务语义）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

from .hash import compute_outbox_id
from .protocol import OutboxRecord


def make_outbox(
    *,
    order_id: str,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    salt: str = "",
) -> OutboxRecord:
    now = datetime.now(timezone.utc).isoformat()
    return OutboxRecord(
        outbox_id=compute_outbox_id(order_id, event_type, salt=salt or now),
        aggregate_type="ORDER",
        aggregate_id=order_id,
        event_type=event_type,
        status="PENDING",
        payload_json=dict(payload or {}),
        created_at=now,
    )


class OutboxService:
    """本地 Outbox 编排；持久化由 Registry 承担。"""

    def __init__(
        self,
        *,
        enqueue_fn: Callable[[OutboxRecord], None],
        list_fn: Callable[[int], Sequence[OutboxRecord]],
        mark_fn: Callable[[str, str], None],
    ) -> None:
        self._enqueue = enqueue_fn
        self._list = list_fn
        self._mark = mark_fn

    def enqueue(self, record: OutboxRecord) -> OutboxRecord:
        self._enqueue(record)
        return record

    def drain(
        self,
        handler: Callable[[OutboxRecord], None],
        *,
        limit: int = 100,
    ) -> int:
        """处理 PENDING；成功 SENT，异常 FAILED。"""
        pending = list(self._list(limit))
        n = 0
        for rec in pending:
            if str(rec.status) != "PENDING":
                continue
            try:
                handler(rec)
                self._mark(rec.outbox_id, "SENT")
                n += 1
            except Exception:
                self._mark(rec.outbox_id, "FAILED")
        return n
