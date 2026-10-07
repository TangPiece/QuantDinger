"""Phase 8G：StrategyRuntimeState 加载与默认构造。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .protocol import LifecyclePhase, RuntimeStatus, StrategyRuntimeState, ThrottleTier


def default_runtime_state(
    strategy_code: str,
    *,
    lifecycle_phase: LifecyclePhase = "UNKNOWN",
) -> StrategyRuntimeState:
    return StrategyRuntimeState(
        strategy_code=strategy_code,
        runtime_status="ACTIVE",
        lifecycle_phase=lifecycle_phase,
        throttle_tier="NORMAL",
        throttle_multiplier=1.0,
    )


def load_runtime_state(
    registry: ResearchRegistry,
    strategy_code: str,
    *,
    default_lifecycle: LifecyclePhase = "UNKNOWN",
) -> StrategyRuntimeState:
    try:
        row = registry.get_strategy_runtime_state(strategy_code)
    except Exception:
        return default_runtime_state(strategy_code, lifecycle_phase=default_lifecycle)
    return StrategyRuntimeState(
        strategy_code=row.strategy_code,
        runtime_status=row.runtime_status,  # type: ignore[arg-type]
        lifecycle_phase=row.lifecycle_phase,  # type: ignore[arg-type]
        throttle_tier=row.throttle_tier,  # type: ignore[arg-type]
        throttle_multiplier=float(row.throttle_multiplier or 1.0),
        policy_id=row.policy_id or "",
        policy_version=row.policy_version or "",
        policy_content_hash=row.policy_content_hash or "",
        last_incident_id=row.last_incident_id or "",
        recovery_check_passed=bool(row.recovery_check_passed),
        last_evaluated_at=row.last_evaluated_at or "",
        session_id=row.session_id or "",
        storage_uri=row.storage_uri or "",
        metadata=dict(row.metadata or {}),
    )


def runtime_for_throttle(tier: ThrottleTier) -> tuple[RuntimeStatus, float]:
    mapping: dict[ThrottleTier, tuple[RuntimeStatus, float]] = {
        "NORMAL": ("ACTIVE", 1.0),
        "THROTTLED_75": ("THROTTLED", 0.75),
        "THROTTLED_50": ("THROTTLED", 0.50),
        "THROTTLED_25": ("THROTTLED", 0.25),
        "PAUSED": ("PAUSED", 0.0),
    }
    return mapping.get(tier, ("THROTTLED", 0.75))


__all__ = ["default_runtime_state", "load_runtime_state", "runtime_for_throttle"]
