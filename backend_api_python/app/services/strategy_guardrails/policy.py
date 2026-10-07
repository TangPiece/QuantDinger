"""Phase 8G：GuardrailPolicy / AutoActionPolicy Registry 解析。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .policy_presets import get_default_preset
from .protocol import ActionMatrixEntry, AutoActionPolicyRecord, GuardrailPolicyRecord


def resolve_guardrail_policies(
    registry: ResearchRegistry,
) -> tuple[GuardrailPolicyRecord, AutoActionPolicyRecord]:
    """缺省 default_guardrail_v1；存在则读 Registry。"""
    from app.services.research_data.contracts import (
        AutoActionPolicySummary,
        GuardrailPolicySummary,
    )

    guard_preset, auto_preset = get_default_preset()
    try:
        grow = registry.get_guardrail_policy(
            guard_preset.policy_id, guard_preset.policy_version
        )
        guard = GuardrailPolicyRecord(
            policy_id=grow.policy_id,
            policy_version=grow.policy_version,
            policy_content_hash=grow.policy_content_hash,
            auto_execute=bool(grow.auto_execute),
            auto_action_policy_id=grow.auto_action_policy_id,
            auto_action_policy_version=grow.auto_action_policy_version,
            action_matrix=[
                ActionMatrixEntry.model_validate(e) for e in (grow.action_matrix_json or [])
            ],
            engine_version=grow.engine_version or guard_preset.engine_version,
            description=grow.description or guard_preset.description,
        )
    except Exception:
        guard = guard_preset
        registry.upsert_guardrail_policy(
            GuardrailPolicySummary(
                policy_id=guard.policy_id,
                policy_version=guard.policy_version,
                policy_content_hash=guard.policy_content_hash,
                auto_execute=guard.auto_execute,
                auto_action_policy_id=guard.auto_action_policy_id,
                auto_action_policy_version=guard.auto_action_policy_version,
                action_matrix_json=[e.model_dump(mode="json") for e in guard.action_matrix],
                engine_version=guard.engine_version,
                description=guard.description,
            )
        )
    try:
        arow = registry.get_auto_action_policy(
            guard.auto_action_policy_id or auto_preset.policy_id,
            guard.auto_action_policy_version or auto_preset.policy_version,
        )
        auto = AutoActionPolicyRecord(
            policy_id=arow.policy_id,
            policy_version=arow.policy_version,
            policy_content_hash=arow.policy_content_hash,
            auto_allowed=list(arow.auto_allowed_json or []),
            auto_forbidden=list(arow.auto_forbidden_json or []),
            auto_resume=bool(arow.auto_resume),
            engine_version=arow.engine_version or auto_preset.engine_version,
            description=arow.description or auto_preset.description,
        )
    except Exception:
        auto = auto_preset
        registry.upsert_auto_action_policy(
            AutoActionPolicySummary(
                policy_id=auto.policy_id,
                policy_version=auto.policy_version,
                policy_content_hash=auto.policy_content_hash,
                auto_allowed_json=list(auto.auto_allowed),
                auto_forbidden_json=list(auto.auto_forbidden),
                auto_resume=auto.auto_resume,
                engine_version=auto.engine_version,
                description=auto.description,
            )
        )
    return guard, auto


__all__ = ["resolve_guardrail_policies"]
