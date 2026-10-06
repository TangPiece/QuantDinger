"""写入 AuditEvent；禁止覆盖已有事件内容。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..hash import checksum_payload, derive_audit_event_id
from ..protocol import AuditActor, AuditEvent


class AppendOnlyConflict(RuntimeError):
    """尝试改写已存在的 audit event。"""


def emit_audit(
    writer: Any,
    *,
    event_type: str,
    actor: AuditActor | None = None,
    trace_id: str = "",
    account_id: str = "",
    strategy_id: str = "",
    order_id: str = "",
    entity_type: str = "",
    entity_id: str = "",
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
    metadata: dict | None = None,
    event_id: str = "",
    salt: str = "",
) -> AuditEvent:
    """emit + 持久化；同 event_id 且 payload 不同则抛 AppendOnlyConflict。"""
    now = datetime.now(timezone.utc).isoformat()
    eid = event_id or derive_audit_event_id(
        event_type=event_type,
        trace_id=trace_id,
        entity_id=entity_id or order_id,
        salt=salt,
    )
    ev = AuditEvent(
        event_id=eid,
        event_type=event_type,
        timestamp=now,
        actor=actor or AuditActor(),
        trace_id=trace_id,
        account_id=account_id,
        strategy_id=strategy_id,
        order_id=order_id,
        entity_type=entity_type,
        entity_id=entity_id,
        before=dict(before or {}),
        after=dict(after or {}),
        reason=reason,
        metadata=dict(metadata or {}),
    )
    if writer.audit_exists(eid):
        existing = writer.get_audit_event(eid)
        if checksum_payload(existing) != checksum_payload(ev):
            raise AppendOnlyConflict(f"audit event {eid!r} already exists")
        return existing
    writer.write_audit_event(ev)
    return ev
