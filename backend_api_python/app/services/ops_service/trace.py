"""trace_id 贯穿 OrderIntent → Order → Fill 审计链。"""

from __future__ import annotations

from typing import Any, Optional

from app.services.research_data.contracts import OrderIntent

from .hash import derive_trace_id


def ensure_trace_id(
    intent: OrderIntent,
    *,
    seed: str = "",
    salt: str = "",
) -> str:
    """为 OrderIntent 补齐 trace_id（字段优先，否则 metadata）。"""
    existing = str(getattr(intent, "trace_id", "") or "").strip()
    if existing:
        return existing
    tid = derive_trace_id(seed=seed, salt=salt)
    intent.trace_id = tid
    return tid


def trace_id_from_intent(intent: OrderIntent | Any) -> str:
    """读取 intent 上已有 trace_id。"""
    return str(getattr(intent, "trace_id", "") or "").strip()


def get_trace(
    writer: Any,
    trace_id: str,
    *,
    limit: int = 500,
) -> list:
    """按 trace_id 拉审计事件（时间升序）。"""
    if not trace_id:
        return []
    rows = writer.list_audit_events(trace_id=trace_id, limit=limit)
    return sorted(rows, key=lambda e: str(getattr(e, "timestamp", "") or ""))
