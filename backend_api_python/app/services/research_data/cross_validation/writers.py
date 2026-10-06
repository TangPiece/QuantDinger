"""CrossValidation → 本地 Summary + Registry。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import CrossValidationSummary
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import CrossValidationArtifactStore
from .protocol import (
    ENGINE_VERSION,
    CrossValidationManifest,
    CrossValidationReport,
    CrossValidationSpec,
)


class CrossValidationWriter:
    """写 manifest / report + Registry。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: CrossValidationArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or CrossValidationArtifactStore()

    def write(
        self,
        spec: CrossValidationSpec,
        *,
        cv_hash: str,
        report: CrossValidationReport,
        force: bool = False,
    ) -> CrossValidationSummary:
        if not force:
            try:
                return self._registry.get_research_cross_validation(cv_hash)
            except (KeyError, AttributeError):
                pass

        layer_map: dict[str, Any] = {
            L.layer: L.model_dump(mode="json") for L in report.layers
        }
        summary = CrossValidationSummary(
            cv_hash=cv_hash,
            strategy_hash=spec.strategy_hash,
            backtest_hash=report.backtest_hash,
            qlib_run_hash=report.qlib_run_hash,
            start_date=report.start_date,
            end_date=report.end_date,
            realism=report.realism,
            execution_policy=spec.execution_policy.mode,
            status=report.status,
            layer_results_json=layer_map,
            attribution_json=report.attribution.model_dump(mode="json"),
            metrics_side_by_side_json=dict(report.side_by_side or {}),
            engine_version=spec.cv_engine_version or ENGINE_VERSION,
            metadata=dict(report.metadata or {}),
        )
        man = CrossValidationManifest(
            cv_hash=cv_hash,
            strategy_hash=spec.strategy_hash,
            engine_version=summary.engine_version,
        )
        art = self._artifacts.write_manifest(man, summary=summary, report=report)
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_research_cross_validation(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary
