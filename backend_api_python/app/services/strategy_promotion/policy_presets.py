"""Phase 8D：内置 PromotionPolicy preset（按 transition 版本化）。"""

from __future__ import annotations

from .pin import policy_content_hash
from .protocol import PromotionPolicyRecord, PromotionPolicyRules

REGISTERED_TO_SHADOW_ID = "registered_to_shadow_v1"
SHADOW_TO_CL_ID = "shadow_to_controlled_live_v1"
CL_TO_LIVE_ID = "controlled_live_to_live_v1"
DEFAULT_POLICY_VERSION = "v1"


def _rules_registered_shadow() -> PromotionPolicyRules:
    return PromotionPolicyRules(
        require_validation_passed=True,
        required_approval=False,
    )


def _rules_shadow_cl() -> PromotionPolicyRules:
    return PromotionPolicyRules(
        require_validation_passed=True,
        min_shadow_days=1.0,
        max_shadow_drawdown=0.2,
        max_shadow_drift=0.12,
        max_recon_errors=0,
        required_approval=False,
    )


def _rules_cl_live() -> PromotionPolicyRules:
    return PromotionPolicyRules(
        require_validation_passed=True,
        min_controlled_days=1.0,
        max_live_drawdown=0.15,
        max_slippage=0.04,
        max_reject_rate=0.08,
        max_risk_breach=0,
        required_approval_count=1,
        require_l4_scale=True,
        required_approval=True,
    )


def registered_to_shadow_v1() -> PromotionPolicyRecord:
    pid = REGISTERED_TO_SHADOW_ID
    pver = DEFAULT_POLICY_VERSION
    tk = "REGISTERED→SHADOW"
    rules = _rules_registered_shadow()
    return PromotionPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        transition_key=tk,
        policy_content_hash=policy_content_hash(
            policy_id=pid, policy_version=pver, transition_key=tk, rules=rules
        ),
        rules=rules,
        description="REGISTERED → SHADOW 默认策略",
    )


def shadow_to_controlled_live_v1() -> PromotionPolicyRecord:
    pid = SHADOW_TO_CL_ID
    pver = DEFAULT_POLICY_VERSION
    tk = "SHADOW→CONTROLLED_LIVE"
    rules = _rules_shadow_cl()
    return PromotionPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        transition_key=tk,
        policy_content_hash=policy_content_hash(
            policy_id=pid, policy_version=pver, transition_key=tk, rules=rules
        ),
        rules=rules,
        description="SHADOW → CONTROLLED_LIVE 默认策略",
    )


def controlled_live_to_live_v1() -> PromotionPolicyRecord:
    pid = CL_TO_LIVE_ID
    pver = DEFAULT_POLICY_VERSION
    tk = "CONTROLLED_LIVE→LIVE"
    rules = _rules_cl_live()
    return PromotionPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        transition_key=tk,
        policy_content_hash=policy_content_hash(
            policy_id=pid, policy_version=pver, transition_key=tk, rules=rules
        ),
        rules=rules,
        description="CONTROLLED_LIVE → LIVE（须人工审批 + L4）",
    )


_PRESETS: dict[str, PromotionPolicyRecord] = {
    "REGISTERED→SHADOW": registered_to_shadow_v1(),
    "SHADOW→CONTROLLED_LIVE": shadow_to_controlled_live_v1(),
    "CONTROLLED_LIVE→LIVE": controlled_live_to_live_v1(),
}


def transition_key(from_env: str, to_env: str) -> str:
    return f"{str(from_env).upper()}→{str(to_env).upper()}"


def get_preset_for_transition(from_env: str, to_env: str) -> PromotionPolicyRecord:
    key = transition_key(from_env, to_env)
    if key not in _PRESETS:
        raise KeyError(f"unknown promotion transition preset: {key}")
    return _PRESETS[key].model_copy(deep=True)


def list_presets() -> list[PromotionPolicyRecord]:
    return [p.model_copy(deep=True) for p in _PRESETS.values()]


__all__ = [
    "CL_TO_LIVE_ID",
    "DEFAULT_POLICY_VERSION",
    "REGISTERED_TO_SHADOW_ID",
    "SHADOW_TO_CL_ID",
    "controlled_live_to_live_v1",
    "get_preset_for_transition",
    "list_presets",
    "registered_to_shadow_v1",
    "shadow_to_controlled_live_v1",
    "transition_key",
]
