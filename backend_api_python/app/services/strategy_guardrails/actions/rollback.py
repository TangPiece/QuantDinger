"""Phase 8G：ROLLBACK → lineage GuardrailRollbackRecord。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..bridges.promotion import run_promotion_rollback
from ..fsm import assert_runtime_transition
from ..identity import build_rollback_id
from ..protocol import GuardrailRollbackRecord, StrategyRuntimeState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_rollback(
    runtime: StrategyRuntimeState,
    *,
    to_version: str,
    reason: str,
    operator: str,
    decision_id: str = "",
    promotion: Any | None = None,
    governance: Any | None = None,
    from_version: str = "",
    from_model_version: str = "",
    to_model_version: str = "",
    from_dataset_hash: str = "",
    to_dataset_hash: str = "",
    session_id: str = "",
) -> tuple[StrategyRuntimeState, GuardrailRollbackRecord]:
    assert_runtime_transition(runtime.runtime_status, "ROLLBACK_PENDING")
    promo_rec = run_promotion_rollback(
        promotion,
        strategy_code=runtime.strategy_code,
        to_version=to_version,
        reason=reason,
        operator=operator,
        governance=governance,
        from_version=from_version,
    )
    ts = _now()
    active_from = from_version or getattr(promo_rec, "from_version", "") or ""
    record = GuardrailRollbackRecord(
        rollback_id=build_rollback_id(
            strategy_code=runtime.strategy_code,
            to_version=to_version,
            created_at=ts,
        ),
        strategy_code=runtime.strategy_code,
        from_version=active_from,
        to_version=to_version,
        from_model_version=from_model_version,
        to_model_version=to_model_version,
        from_dataset_hash=from_dataset_hash,
        to_dataset_hash=to_dataset_hash,
        decision_id=decision_id,
        reason=reason,
        operator=operator,
        session_id=session_id,
        created_at=ts,
        metadata={"promotion_rollback_id": getattr(promo_rec, "rollback_id", "")},
    )
    new_rt = runtime.model_copy(
        update={
            "runtime_status": "ROLLING_BACK",
            "recovery_check_passed": False,
        }
    )
    assert_runtime_transition("ROLLING_BACK", "PAUSED")
    new_rt = new_rt.model_copy(update={"runtime_status": "PAUSED"})
    return new_rt, record


__all__ = ["apply_rollback"]
