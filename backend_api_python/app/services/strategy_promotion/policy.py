"""Phase 8D：PromotionPolicy content_hash 与 Registry 解析。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .policy_presets import get_preset_for_transition, list_presets, transition_key
from .protocol import PromotionPolicyRecord, PromotionPolicyRules


def resolve_policy_for_transition(
    registry: ResearchRegistry,
    from_env: str,
    to_env: str,
    *,
    policy_id: str | None = None,
    policy_version: str | None = None,
) -> PromotionPolicyRecord:
    """按 transition 解析 policy；缺省用内置 preset 并 upsert Registry。"""
    from app.services.research_data.contracts import StrategyPromotionPolicySummary

    preset = get_preset_for_transition(from_env, to_env)
    pid = str(policy_id or preset.policy_id).strip()
    pver = str(policy_version or preset.policy_version).strip()
    if pid != preset.policy_id or pver != preset.policy_version:
        preset = get_preset_for_transition(from_env, to_env)
    try:
        row = registry.get_strategy_promotion_policy(pid, pver)
        return PromotionPolicyRecord(
            policy_id=row.policy_id,
            policy_version=row.policy_version,
            transition_key=row.transition_key or transition_key(from_env, to_env),
            policy_content_hash=row.policy_content_hash,
            rules=PromotionPolicyRules.model_validate(row.rules_json or {}),
            engine_version=row.engine_version or preset.engine_version,
            description=row.description or preset.description,
        )
    except Exception:
        registry.upsert_strategy_promotion_policy(
            StrategyPromotionPolicySummary(
                policy_id=preset.policy_id,
                policy_version=preset.policy_version,
                transition_key=preset.transition_key,
                policy_content_hash=preset.policy_content_hash,
                rules_json=preset.rules.model_dump(mode="json"),
                engine_version=preset.engine_version,
                description=preset.description,
            )
        )
        return preset


def list_all_policies(registry: ResearchRegistry) -> list[PromotionPolicyRecord]:
    seen: set[tuple[str, str]] = set()
    out: list[PromotionPolicyRecord] = []
    for preset in list_presets():
        out.append(preset)
        seen.add((preset.policy_id, preset.policy_version))
    try:
        rows = registry.list_strategy_promotion_policies()
    except Exception:
        rows = []
    for row in rows:
        key = (row.policy_id, row.policy_version)
        if key in seen:
            continue
        out.append(
            PromotionPolicyRecord(
                policy_id=row.policy_id,
                policy_version=row.policy_version,
                transition_key=row.transition_key,
                policy_content_hash=row.policy_content_hash,
                rules=PromotionPolicyRules.model_validate(row.rules_json or {}),
                engine_version=row.engine_version,
                description=row.description or "",
            )
        )
    out.sort(key=lambda p: (p.policy_id, p.policy_version))
    return out


__all__ = ["list_all_policies", "resolve_policy_for_transition"]
