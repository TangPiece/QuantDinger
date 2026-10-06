"""审计查询封装。"""

from __future__ import annotations

from typing import Any


def list_audit_events(
    writer: Any,
    *,
    account_id: str = "",
    strategy_id: str = "",
    order_id: str = "",
    trace_id: str = "",
    event_type: str = "",
    limit: int = 200,
) -> list:
    return writer.list_audit_events(
        account_id=account_id,
        strategy_id=strategy_id,
        order_id=order_id,
        trace_id=trace_id,
        event_type=event_type,
        limit=limit,
    )
