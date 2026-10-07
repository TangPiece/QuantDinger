"""Phase 6J：Readiness → Registry + R2。"""

from __future__ import annotations

from app.services.research_data.contracts import (
    ReadinessCheckResultSummary,
    ReadinessRunSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ReadinessArtifactStore
from .protocol import ChecklistResult, ENGINE_VERSION, ReadinessCheck, ScenarioResult


class ReadinessWriter:
    """Checklist / 场景结果索引。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ReadinessArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ReadinessArtifactStore()

    def write_checklist(self, result: ChecklistResult) -> ReadinessRunSummary:
        meta = dict(result.metadata or {})
        uri, cs = self._artifacts.write_checklist(result)
        meta["storage_uri"] = uri
        meta["checksum"] = cs
        summary = ReadinessRunSummary(
            run_id=result.run_id,
            production_ready=bool(result.production_ready),
            engine_version=ENGINE_VERSION,
            metadata=meta,
        )
        self._registry.upsert_readiness_run(summary)
        for chk in result.checks:
            self._registry.upsert_readiness_check_result(
                ReadinessCheckResultSummary(
                    check_result_id=f"{result.run_id}|{chk.check_id}",
                    run_id=result.run_id,
                    check_id=chk.check_id,
                    scenario_id=chk.scenario_id,
                    status=str(chk.status),
                    title=chk.title,
                    engine_version=ENGINE_VERSION,
                    metadata={
                        "messages": list(chk.messages),
                        **dict(chk.metadata or {}),
                    },
                )
            )
        return summary

    def write_scenario_result(self, result: ScenarioResult, *, run_id: str) -> None:
        self._registry.upsert_readiness_check_result(
            ReadinessCheckResultSummary(
                check_result_id=result.scenario_run_id,
                run_id=run_id,
                check_id=result.scenario_id,
                scenario_id=result.scenario_id,
                status=str(result.status),
                title=result.scenario_id,
                engine_version=ENGINE_VERSION,
                metadata={
                    "order_ids": list(result.order_ids),
                    "messages": list(result.messages),
                    **dict(result.metadata or {}),
                },
            )
        )
