"""Phase 8D：Shadow / Controlled-Live session 桩（记录 session_id，不发 OMS）。"""

from __future__ import annotations

from uuid import uuid4


def open_shadow_session(*, strategy_code: str, strategy_version: str) -> str:
    """Fake Shadow session：仅返回确定性风格 session_id。"""
    safe = str(strategy_code or "unknown").replace("/", "_")
    return f"shadow_{safe}_{uuid4().hex[:12]}"


def open_controlled_live_session(*, strategy_code: str, strategy_version: str) -> str:
    """Fake CL session。"""
    safe = str(strategy_code or "unknown").replace("/", "_")
    return f"cl_{safe}_{uuid4().hex[:12]}"


def open_rollback_session(*, strategy_code: str, to_version: str) -> str:
    safe = str(strategy_code or "unknown").replace("/", "_")
    return f"rb_sess_{safe}_{uuid4().hex[:10]}"


__all__ = [
    "open_controlled_live_session",
    "open_rollback_session",
    "open_shadow_session",
]
