"""Phase 8C：ValidationPolicy 解析与 Registry 同步。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .policy_presets import get_preset, list_presets
from .protocol import ValidationPolicyRecord, ValidationPolicyRules


def resolve_policy(
    registry: ResearchRegistry,
    policy_id: str,
    policy_version: str | None = None,
) -> ValidationPolicyRecord:
    """优先 Registry；缺失则 seed 内置 preset 并 upsert。"""
    from app.services.research_data.contracts import StrategyValidationPolicySummary

    pid = str(policy_id or "").strip()
    preset = get_preset(pid, policy_version)
    pver = preset.policy_version
    try:
        row = registry.get_strategy_validation_policy(pid, pver)
        return ValidationPolicyRecord(
            policy_id=row.policy_id,
            policy_version=row.policy_version,
            policy_content_hash=row.policy_content_hash,
            rules=ValidationPolicyRules.model_validate(
                row.rules_json or preset.rules.model_dump(mode="json")
            ),
            engine_version=row.engine_version or preset.engine_version,
            description=row.description or preset.description,
        )
    except Exception:
        registry.upsert_strategy_validation_policy(
            StrategyValidationPolicySummary(
                policy_id=preset.policy_id,
                policy_version=preset.policy_version,
                policy_content_hash=preset.policy_content_hash,
                rules_json=preset.rules.model_dump(mode="json"),
                engine_version=preset.engine_version,
                description=preset.description,
            )
        )
        return preset


def list_all_policies(registry: ResearchRegistry) -> list[ValidationPolicyRecord]:
    """合并 preset 与 Registry 已登记策略。"""
    seen: set[tuple[str, str]] = set()
    out: list[ValidationPolicyRecord] = []
    for preset in list_presets():
        out.append(preset)
        seen.add((preset.policy_id, preset.policy_version))
    try:
        rows = registry.list_strategy_validation_policies()
    except Exception:
        rows = []
    for row in rows:
        key = (row.policy_id, row.policy_version)
        if key in seen:
            continue
        out.append(
            ValidationPolicyRecord(
                policy_id=row.policy_id,
                policy_version=row.policy_version,
                policy_content_hash=row.policy_content_hash,
                rules=ValidationPolicyRules.model_validate(row.rules_json or {}),
                engine_version=row.engine_version,
                description=row.description or "",
            )
        )
    out.sort(key=lambda p: (p.policy_id, p.policy_version))
    return out


__all__ = ["list_all_policies", "resolve_policy"]
