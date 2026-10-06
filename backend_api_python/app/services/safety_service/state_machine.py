"""Safety 状态机：NORMAL→DEGRADED→HALTED；EMERGENCY；Resume 约束。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .protocol import SafetyState, SafetyStateName

# 合法迁移（不含自动 EMERGENCY→NORMAL）
_TRANSITIONS: dict[str, frozenset[str]] = {
    "UNKNOWN": frozenset({"NORMAL", "DEGRADED", "HALTED", "EMERGENCY"}),
    "NORMAL": frozenset({"DEGRADED", "HALTED", "EMERGENCY", "UNKNOWN"}),
    "DEGRADED": frozenset({"NORMAL", "HALTED", "EMERGENCY", "UNKNOWN"}),
    "HALTED": frozenset({"NORMAL", "DEGRADED", "EMERGENCY", "UNKNOWN"}),
    "EMERGENCY": frozenset({"HALTED", "NORMAL", "UNKNOWN"}),  # NORMAL 仅经 resume
}


class SafetyStateError(RuntimeError):
    """非法状态迁移或恢复。"""


def assert_transition(current: str, target: str) -> None:
    allowed = _TRANSITIONS.get(str(current).upper(), frozenset())
    if str(target).upper() not in allowed:
        raise SafetyStateError(
            f"illegal safety transition {current!r} → {target!r}"
        )


def is_blocking_state(state: str) -> bool:
    """HALTED / EMERGENCY / UNKNOWN 均阻断新单。"""
    return str(state).upper() in ("HALTED", "EMERGENCY", "UNKNOWN")


def transition(
    st: SafetyState,
    target: SafetyStateName,
    *,
    reason: str = "",
    force: bool = False,
) -> SafetyState:
    """推进状态；默认校验迁移表。"""
    if not force:
        assert_transition(st.state, target)
    meta = dict(st.metadata or {})
    if reason:
        meta["last_reason"] = reason
    return st.model_copy(
        update={
            "state": target,
            "reason": reason or st.reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False if target != "NORMAL" else st.acknowledged,
            "metadata": meta,
        }
    )


def require_ack_for_resume(st: SafetyState) -> None:
    """CRITICAL 类状态恢复前必须已 acknowledge。"""
    if str(st.state).upper() in ("HALTED", "EMERGENCY"):
        if not st.acknowledged:
            raise SafetyStateError(
                "resume requires operator acknowledge for HALTED/EMERGENCY"
            )


def acknowledge_state(st: SafetyState, *, operator: str = "") -> SafetyState:
    meta = dict(st.metadata or {})
    if operator:
        meta["acknowledged_by"] = operator
    return st.model_copy(
        update={
            "acknowledged": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": meta,
        }
    )


def resume_state(st: SafetyState, *, operator: str = "") -> SafetyState:
    """人工恢复 → NORMAL。"""
    require_ack_for_resume(st)
    assert_transition(st.state, "NORMAL")
    meta = dict(st.metadata or {})
    meta["resumed_by"] = operator
    return st.model_copy(
        update={
            "state": "NORMAL",
            "acknowledged": False,
            "reason": "resumed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": meta,
        }
    )
