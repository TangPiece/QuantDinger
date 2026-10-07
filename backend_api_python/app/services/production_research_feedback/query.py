"""Phase 8H：ResearchFeedbackQuery（只读；Actual / Counterfactual 分桶）。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .protocol import ResearchFeedbackQuery, ResearchFeedbackRecord


def execute_feedback_query(
    registry: ResearchRegistry,
    query: ResearchFeedbackQuery,
) -> list[ResearchFeedbackRecord]:
    out: list[ResearchFeedbackRecord] = []
    code = str(query.strategy_code or "").strip()
    ftype = str(query.feedback_type or "").strip().upper()
    reality = query.reality_kind
    limit = max(1, min(int(query.limit or 100), 500))

    if query.dataset_id:
        try:
            row = registry.get_production_feedback_dataset(query.dataset_id)
        except KeyError:
            return []
        if code and row.strategy_code != code:
            return []
        if ftype and row.feedback_type != ftype:
            return []
        out.append(
            ResearchFeedbackRecord(
                record_kind="DATASET",
                strategy_code=row.strategy_code,
                dataset_id=row.dataset_id,
                feedback_type=row.feedback_type,
                reality_kind="ACTUAL",
                dataset_hash=row.dataset_hash,
                payload={
                    "window_start": row.window_start,
                    "window_end": row.window_end,
                    "lineage": row.lineage_json,
                },
            )
        )
        return out[:limit]

    datasets = registry.list_production_feedback_datasets(code or None)
    for row in datasets:
        if ftype and row.feedback_type != ftype:
            continue
        if query.window_start and (row.window_end or "") < query.window_start:
            continue
        if query.window_end and (row.window_start or "") > query.window_end:
            continue
        out.append(
            ResearchFeedbackRecord(
                record_kind="DATASET",
                strategy_code=row.strategy_code,
                dataset_id=row.dataset_id,
                feedback_type=row.feedback_type,
                reality_kind="ACTUAL",
                dataset_hash=row.dataset_hash,
                payload={"lineage": row.lineage_json},
            )
        )

    if reality == "ACTUAL":
        snaps = registry.list_production_reality_snapshots(code or None, reality_kind="ACTUAL")
        for row in snaps:
            out.append(
                ResearchFeedbackRecord(
                    record_kind="SNAPSHOT",
                    strategy_code=row.strategy_code,
                    snapshot_id=row.snapshot_id,
                    reality_kind="ACTUAL",
                    as_of_time=row.as_of_time or "",
                    payload={
                        "pnl_total": row.pnl_total,
                        "metrics": row.metrics_json,
                        "snapshot_version": row.snapshot_version,
                    },
                )
            )
    else:
        # Counterfactual 仅返回 COUNTERFACTUAL 桶（不含 Actual PnL）
        snaps = registry.list_production_reality_snapshots(code or None, reality_kind="COUNTERFACTUAL")
        for row in snaps:
            out.append(
                ResearchFeedbackRecord(
                    record_kind="COUNTERFACTUAL",
                    strategy_code=row.strategy_code,
                    snapshot_id=row.snapshot_id,
                    reality_kind="COUNTERFACTUAL",
                    payload={"metrics": row.metrics_json},
                )
            )

    cases = registry.list_research_failure_cases(code or None)
    for row in cases:
        out.append(
            ResearchFeedbackRecord(
                record_kind="FAILURE_CASE",
                strategy_code=row.strategy_code,
                case_id=row.case_id,
                dataset_hash=row.dataset_hash,
                payload={
                    "incident_id": row.incident_id,
                    "summary": row.summary,
                },
            )
        )

    return out[:limit]


__all__ = ["execute_feedback_query"]
