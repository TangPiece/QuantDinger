"""Phase 8H：Counterfactual 生成（与 Actual PnL 严格隔离）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .identity import build_counterfactual_id
from .protocol import CounterfactualRecord, ENGINE_VERSION, ProductionRealitySnapshot


class CounterfactualError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_counterfactual_record(
    registry: ResearchRegistry,
    *,
    snapshot_id: str,
    scenario: Mapping[str, Any],
    session_id: str = "",
) -> CounterfactualRecord:
    sid = str(snapshot_id or "").strip()
    try:
        row = registry.get_production_reality_snapshot(sid)
    except KeyError as exc:
        raise CounterfactualError(f"snapshot missing: {sid}") from exc
    if row.reality_kind != "ACTUAL":
        raise CounterfactualError("counterfactual parent must be ACTUAL snapshot")

    scenario_key = str(scenario.get("name") or scenario.get("key") or "default")
    record_id = build_counterfactual_id(parent_snapshot_id=sid, scenario_key=scenario_key)
    shock = float(scenario.get("pnl_shock") or 0.0)
    base_pnl = float(row.pnl_total or 0.0)
    simulated = {
        "simulated_pnl_total": base_pnl + shock,
        "shock_applied": shock,
    }
    return CounterfactualRecord(
        record_id=record_id,
        parent_snapshot_id=sid,
        strategy_code=row.strategy_code,
        reality_kind="COUNTERFACTUAL",
        scenario=dict(scenario),
        simulated_summary=simulated,
        created_at=_now(),
        session_id=session_id,
        engine_version=ENGINE_VERSION,
        metadata={"isolated_from_actual_pnl": True},
    )


def counterfactual_snapshot_stub(
    parent: ProductionRealitySnapshot,
    *,
    record: CounterfactualRecord,
) -> ProductionRealitySnapshot:
    """可选：将 Counterfactual 摘要写入独立 snapshot 桶（metrics 无 actual pnl）。"""
    return ProductionRealitySnapshot(
        snapshot_id=f"{parent.snapshot_id}_cf_{record.record_id[-8:]}",
        snapshot_version=1,
        supersedes_snapshot_id="",
        strategy_code=parent.strategy_code,
        reality_kind="COUNTERFACTUAL",
        as_of_time=parent.as_of_time,
        pnl_summary=parent.pnl_summary.model_copy(update={"pnl_total": 0.0}),
        metrics=dict(record.simulated_summary),
        dataset_id=parent.dataset_id,
        lineage=parent.lineage,
        content_hash=record.record_id,
        created_at=record.created_at,
        session_id=record.session_id,
        engine_version=ENGINE_VERSION,
        metadata={"counterfactual_record_id": record.record_id},
    )


__all__ = [
    "CounterfactualError",
    "build_counterfactual_record",
    "counterfactual_snapshot_stub",
]
