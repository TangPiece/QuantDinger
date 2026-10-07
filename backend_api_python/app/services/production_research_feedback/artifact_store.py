"""Phase 8H：Production Research Feedback R2 / 本地 JSON 工件。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import (
    CounterfactualRecord,
    FeedbackExperimentLink,
    ProductionFeedbackDataset,
    ProductionRealitySnapshot,
    ResearchFailureCase,
    ResearchHypothesis,
)


class ProductionResearchFeedbackArtifactStore:
    """``qd/registry/production_research_feedback/{strategy_code}/...``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def _write_local(self, key: str, payload: dict[str, Any]) -> tuple[str, str]:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/production_research_feedback/", 1)[-1]
            fp = self.root / "registry" / "production_research_feedback" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def write_dataset(self, record: ProductionFeedbackDataset) -> tuple[str, str]:
        key = rd_paths.production_research_feedback_dataset_key(
            strategy_code=record.strategy_code,
            dataset_id=record.dataset_id,
        )
        return self._write_local(key, record.model_dump(mode="json"))

    def write_snapshot(self, record: ProductionRealitySnapshot) -> tuple[str, str]:
        key = rd_paths.production_research_feedback_snapshot_key(
            strategy_code=record.strategy_code,
            snapshot_id=record.snapshot_id,
            snapshot_version=record.snapshot_version,
        )
        return self._write_local(key, record.model_dump(mode="json"))

    def write_failure_case(self, record: ResearchFailureCase) -> tuple[str, str]:
        key = rd_paths.production_research_feedback_failure_case_key(
            strategy_code=record.strategy_code,
            case_id=record.case_id,
        )
        return self._write_local(key, record.model_dump(mode="json"))

    def write_hypothesis(self, record: ResearchHypothesis) -> tuple[str, str]:
        key = rd_paths.production_research_feedback_hypothesis_key(
            strategy_code=record.strategy_code,
            hypothesis_id=record.hypothesis_id,
        )
        return self._write_local(key, record.model_dump(mode="json"))

    def write_experiment_link(self, record: FeedbackExperimentLink) -> tuple[str, str]:
        key = rd_paths.production_research_feedback_experiment_link_key(
            strategy_code=record.strategy_code,
            link_id=record.link_id,
        )
        return self._write_local(key, record.model_dump(mode="json"))

    def write_counterfactual(self, record: CounterfactualRecord) -> tuple[str, str]:
        key = rd_paths.production_research_feedback_counterfactual_key(
            strategy_code=record.strategy_code,
            record_id=record.record_id,
        )
        return self._write_local(key, record.model_dump(mode="json"))


__all__ = ["ProductionResearchFeedbackArtifactStore"]
