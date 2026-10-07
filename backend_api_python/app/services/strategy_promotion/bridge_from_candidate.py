"""Phase 8D：从 Candidate + ValidationRun 加载晋升上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.registry import ResearchRegistry

from .preconditions import PreconditionError, assert_validation_passed


@dataclass(frozen=True)
class PromotionEvidenceContext:
    """晋升证据钉扎（只读）。"""

    candidate_id: str
    strategy_code: str
    candidate_version: str
    content_hash: str
    validation_id: str
    validation_status: str
    strategy_version: str
    version_id: str
    registry_content_hash: str


class BridgeFromCandidateError(RuntimeError):
    pass


def load_promotion_context(
    registry: ResearchRegistry,
    *,
    candidate_id: str,
    validation_id: str,
    strategy_version: str,
    candidate_service: Any | None = None,
    strategy_registry: Any | None = None,
) -> PromotionEvidenceContext:
    """加载 Candidate、Validation 与 Registry version 钉扎。"""
    cid = str(candidate_id).strip()
    vid = str(validation_id).strip()
    ver_label = str(strategy_version).strip()
    try:
        assert_validation_passed(registry, validation_id=vid, candidate_id=cid)
    except PreconditionError as exc:
        raise BridgeFromCandidateError(str(exc)) from exc

    if candidate_service is not None:
        cand = candidate_service.get(cid)
    else:
        row = registry.get_strategy_candidate(cid)
        from app.services.strategy_candidate.runner import StrategyCandidateService

        cand = StrategyCandidateService._summary_to_record(row)  # type: ignore[arg-type]

    if strategy_registry is None:
        raise BridgeFromCandidateError("strategy_registry required")
    ver = strategy_registry.get_version(cand.strategy_code, ver_label)
    meta = dict(getattr(ver, "metadata", None) or {})
    cand_hash = str(getattr(cand, "content_hash", "") or "")
    pinned = str(meta.get("content_hash") or cand_hash)
    if pinned != cand_hash:
        raise BridgeFromCandidateError("candidate/registry lineage pin mismatch")
    reg_hash = pinned

    row = registry.get_strategy_validation_run(vid)
    return PromotionEvidenceContext(
        candidate_id=cid,
        strategy_code=str(cand.strategy_code),
        candidate_version=str(cand.candidate_version),
        content_hash=cand_hash,
        validation_id=vid,
        validation_status=str(row.status or ""),
        strategy_version=ver_label,
        version_id=str(getattr(ver, "version_id", "") or ""),
        registry_content_hash=reg_hash or cand_hash,
    )


__all__ = [
    "BridgeFromCandidateError",
    "PromotionEvidenceContext",
    "load_promotion_context",
]
