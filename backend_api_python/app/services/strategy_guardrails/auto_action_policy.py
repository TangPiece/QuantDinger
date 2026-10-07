"""Phase 8G：AutoActionPolicy 解析与自动权限判定。"""

from __future__ import annotations

from .protocol import AutoActionPolicyRecord, GuardrailActionType


def is_auto_allowed(
    policy: AutoActionPolicyRecord,
    action: GuardrailActionType | str,
) -> bool:
    act = str(action or "").strip().upper()
    forbidden = {str(x).upper() for x in policy.auto_forbidden}
    if act in forbidden:
        return False
    allowed = {str(x).upper() for x in policy.auto_allowed}
    if act == "SAFETY_STOP":
        return True
    if act == "REVIEW":
        return False
    return act in allowed


def reject_auto_reason(action: GuardrailActionType | str) -> str:
    act = str(action or "").strip().upper()
    return f"auto {act} forbidden without governance approval"


__all__ = ["is_auto_allowed", "reject_auto_reason"]
