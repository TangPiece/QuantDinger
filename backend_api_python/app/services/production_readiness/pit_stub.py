"""Phase 6J：PIT leakage 桩 — available_time 不得晚于 knowledge_time。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def reject_pit_leakage(
    *,
    available_time: Any,
    knowledge_time: Any,
) -> tuple[bool, str]:
    """返回 (allowed, reason)；available_time > knowledge_time 则拒入 Signal。"""
    avail = parse_ts(available_time)
    know = parse_ts(knowledge_time)
    if avail is None or know is None:
        return True, ""
    if avail > know:
        return False, (
            f"PIT leakage: available_time {avail.isoformat()} "
            f"> knowledge_time {know.isoformat()}"
        )
    return True, ""
