"""Phase 7C：Order metadata 研究链路 stamp。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.research_data.contracts import OrderIntent

from .protocol import ControlledSession


def stamp_lineage(
    *,
    session: ControlledSession,
    intent: OrderIntent,
    strategy_id: str = "",
    signal_id: str = "",
    risk_decision: str = "",
    snapshot_id: str = "",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """绑定 strategy/dataset/model/signal/risk/intent/snapshot 字段。"""
    return {
        "strategy_id": strategy_id or session.approved_strategy_id,
        "dataset_hash": session.dataset_hash,
        "model_version": session.model_version,
        "strategy_version": session.strategy_version or (intent.strategy_version or ""),
        "signal_id": signal_id or (intent.signal_id or ""),
        "trace_id": intent.trace_id or "",
        "risk_decision": risk_decision,
        "snapshot_id": snapshot_id,
        "environment": session.environment,
        "engine_version": session.engine_version,
        **dict(extra or {}),
    }
