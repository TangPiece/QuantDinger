"""Phase 8H：ResearchHypothesis 创建（不触发训练）。"""

from __future__ import annotations

from datetime import datetime, timezone

from .identity import build_hypothesis_id
from .protocol import ENGINE_VERSION, ResearchHypothesis


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_hypothesis(
    *,
    strategy_code: str,
    title: str,
    description: str = "",
    failure_case_ids: list[str] | None = None,
    feedback_dataset_id: str = "",
    session_id: str = "",
    status: str = "DRAFT",
) -> ResearchHypothesis:
    ts = _now()
    hid = build_hypothesis_id(strategy_code=strategy_code, title=title, created_at=ts)
    return ResearchHypothesis(
        hypothesis_id=hid,
        strategy_code=str(strategy_code).strip(),
        status=status,  # type: ignore[arg-type]
        failure_case_ids=list(failure_case_ids or []),
        feedback_dataset_id=str(feedback_dataset_id or ""),
        title=str(title or "").strip(),
        description=str(description or ""),
        created_at=ts,
        session_id=session_id,
        engine_version=ENGINE_VERSION,
    )


__all__ = ["new_hypothesis"]
