"""Phase 8B：PromotionRecord 构造（审计 source → candidate → 8A）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .protocol import PromotionRecord, PromotionSourceType, PromotionToState, StrategyCandidateRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_promotion_id() -> str:
    return f"prom_{uuid.uuid4().hex[:16]}"


def promotion_for_state_change(
    candidate: StrategyCandidateRecord,
    *,
    from_state: str,
    to_state: PromotionToState,
    source_type: PromotionSourceType = "EXPERIMENT",
    source_id: str = "",
    operator: str = "",
    reason: str = "",
) -> PromotionRecord:
    """状态晋升审计（如 GENERATED / VALIDATED）。"""
    sid = source_id or candidate.experiment_id or candidate.backtest_hash or candidate.candidate_id
    return PromotionRecord(
        promotion_id=new_promotion_id(),
        candidate_id=candidate.candidate_id,
        source_type=source_type,
        source_id=sid,
        target_strategy_code=candidate.strategy_code,
        target_strategy_version="",
        version_id="",
        from_state=from_state,
        to_state=to_state,
        dataset_hash=candidate.dataset_hash,
        model_version=candidate.model_version,
        operator=operator,
        reason=reason,
        created_at=_now(),
    )


def promotion_for_registry(
    candidate: StrategyCandidateRecord,
    *,
    target_strategy_version: str,
    version_id: str,
    operator: str,
    reason: str,
) -> PromotionRecord:
    """VALIDATED → 8A register_version_manual 审计。"""
    return PromotionRecord(
        promotion_id=new_promotion_id(),
        candidate_id=candidate.candidate_id,
        source_type="EXPERIMENT" if candidate.experiment_id else "BACKTEST",
        source_id=candidate.experiment_id or candidate.backtest_hash,
        target_strategy_code=candidate.strategy_code,
        target_strategy_version=target_strategy_version,
        version_id=version_id,
        from_state=candidate.status,
        to_state="REGISTERED",
        dataset_hash=candidate.dataset_hash,
        model_version=candidate.model_version,
        operator=operator,
        reason=reason,
        created_at=_now(),
    )


__all__ = ["promotion_for_registry", "promotion_for_state_change"]
