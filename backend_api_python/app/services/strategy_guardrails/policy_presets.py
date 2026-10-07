"""Phase 8G：内置 GuardrailPolicy preset（default_guardrail_v1）。"""

from __future__ import annotations

from .action_matrix import default_action_matrix
from .pin import auto_action_policy_hash, guardrail_policy_hash
from .protocol import AutoActionPolicyRecord, GuardrailPolicyRecord

DEFAULT_GUARDRAIL_POLICY_ID = "default_guardrail_v1"
DEFAULT_AUTO_ACTION_POLICY_ID = "default_auto_action_v1"
DEFAULT_POLICY_VERSION = "v1"


def default_auto_action_v1() -> AutoActionPolicyRecord:
    pid = DEFAULT_AUTO_ACTION_POLICY_ID
    pver = DEFAULT_POLICY_VERSION
    allowed = ["WARN", "THROTTLE", "PAUSE"]
    forbidden = ["STOP", "ROLLBACK", "PROMOTE", "RETIRE", "DEMOTE"]
    return AutoActionPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        policy_content_hash=auto_action_policy_hash(
            policy_id=pid,
            policy_version=pver,
            auto_allowed=allowed,
            auto_forbidden=forbidden,
            auto_resume=False,
        ),
        auto_allowed=allowed,
        auto_forbidden=forbidden,
        auto_resume=False,
        description="默认自动动作白名单（仅 WARN/THROTTLE/PAUSE + Safety 例外）",
    )


def default_guardrail_v1() -> GuardrailPolicyRecord:
    pid = DEFAULT_GUARDRAIL_POLICY_ID
    pver = DEFAULT_POLICY_VERSION
    auto = default_auto_action_v1()
    matrix = default_action_matrix()
    return GuardrailPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        policy_content_hash=guardrail_policy_hash(
            policy_id=pid,
            policy_version=pver,
            auto_execute=True,
            auto_action_policy_id=auto.policy_id,
            auto_action_policy_version=auto.policy_version,
            action_matrix=matrix,
        ),
        auto_execute=True,
        auto_action_policy_id=auto.policy_id,
        auto_action_policy_version=auto.policy_version,
        action_matrix=matrix,
        description="默认 Guardrail（8F → Runtime 保护，Lifecycle 只读）",
    )


def get_default_preset() -> tuple[GuardrailPolicyRecord, AutoActionPolicyRecord]:
    auto = default_auto_action_v1().model_copy(deep=True)
    guard = default_guardrail_v1().model_copy(deep=True)
    return guard, auto


__all__ = [
    "DEFAULT_AUTO_ACTION_POLICY_ID",
    "DEFAULT_GUARDRAIL_POLICY_ID",
    "DEFAULT_POLICY_VERSION",
    "default_auto_action_v1",
    "default_guardrail_v1",
    "get_default_preset",
]
