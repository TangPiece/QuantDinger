"""Phase 8A：Risk / Execution Policy 引用解析与校验。"""

from __future__ import annotations

from .protocol import PolicyBindings


def normalize_policy_bindings(
    *,
    risk_policy_ref: str = "",
    execution_policy_ref: str = "NEXT_OPEN",
) -> PolicyBindings:
    """规范化 policy 引用字符串。"""
    risk = str(risk_policy_ref or "").strip()
    execution = str(execution_policy_ref or "NEXT_OPEN").strip() or "NEXT_OPEN"
    return PolicyBindings(risk_policy_ref=risk, execution_policy_ref=execution)


def merge_bindings(
    base: PolicyBindings,
    *,
    risk_policy_ref: str | None = None,
    execution_policy_ref: str | None = None,
) -> PolicyBindings:
    """合并 policy 补丁（仅用于注册前草稿，注册后不可变）。"""
    return PolicyBindings(
        risk_policy_ref=(
            str(risk_policy_ref).strip()
            if risk_policy_ref is not None
            else base.risk_policy_ref
        ),
        execution_policy_ref=(
            str(execution_policy_ref).strip()
            if execution_policy_ref is not None
            else base.execution_policy_ref
        ),
    )
