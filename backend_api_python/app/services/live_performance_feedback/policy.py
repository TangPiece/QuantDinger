"""Phase 8E：DriftPolicy 解析与 Registry upsert。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .policy_presets import get_default_preset
from .protocol import DriftPolicyRecord, DriftPolicyRule


def resolve_drift_policy(
    registry: ResearchRegistry,
    *,
    policy_id: str | None = None,
    policy_version: str | None = None,
) -> DriftPolicyRecord:
    """缺省 default_drift_v1；存在则读 Registry。"""
    from app.services.research_data.contracts import DriftPolicySummary

    preset = get_default_preset()
    pid = str(policy_id or preset.policy_id).strip()
    pver = str(policy_version or preset.policy_version).strip()
    try:
        row = registry.get_drift_policy(pid, pver)
        rules_raw = row.rules_json or []
        return DriftPolicyRecord(
            policy_id=row.policy_id,
            policy_version=row.policy_version,
            policy_content_hash=row.policy_content_hash,
            rules=[DriftPolicyRule.model_validate(r) for r in rules_raw],
            engine_version=row.engine_version or preset.engine_version,
            description=row.description or preset.description,
        )
    except Exception:
        target = preset if pid == preset.policy_id and pver == preset.policy_version else preset
        registry.upsert_drift_policy(
            DriftPolicySummary(
                policy_id=target.policy_id,
                policy_version=target.policy_version,
                policy_content_hash=target.policy_content_hash,
                rules_json=[r.model_dump(mode="json") for r in target.rules],
                engine_version=target.engine_version,
                description=target.description,
            )
        )
        return target


__all__ = ["resolve_drift_policy"]
