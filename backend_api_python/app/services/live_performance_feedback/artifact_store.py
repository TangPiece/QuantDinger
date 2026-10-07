"""Phase 8E：Performance Feedback R2 / 本地 JSON 工件。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import ExpectedBaseline, PerformanceComparisonRun, ProductionDriftReport


class PerformanceFeedbackArtifactStore:
    """``qd/registry/performance_feedback/{strategy_code}/baselines|runs/{id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def _write_local(self, key: str, payload: dict[str, Any]) -> tuple[str, str]:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/performance_feedback/", 1)[-1]
            fp = self.root / "registry" / "performance_feedback" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def write_baseline(self, baseline: ExpectedBaseline) -> tuple[str, str]:
        key = rd_paths.performance_feedback_baseline_key(
            strategy_code=baseline.strategy_code,
            baseline_id=baseline.baseline_id,
        )
        payload = baseline.model_dump(mode="json")
        return self._write_local(key, payload)

    def write_run(self, run: PerformanceComparisonRun) -> tuple[str, str]:
        key = rd_paths.performance_feedback_run_key(
            strategy_code=run.strategy_code,
            run_id=run.run_id,
        )
        payload = run.model_dump(mode="json")
        return self._write_local(key, payload)

    def write_report(self, report: ProductionDriftReport) -> tuple[str, str]:
        key = rd_paths.performance_feedback_run_key(
            strategy_code=report.strategy_code,
            run_id=report.run_id,
        )
        payload = {"report": report.model_dump(mode="json")}
        return self._write_local(key.replace("/runs/", "/reports/"), payload)


__all__ = ["PerformanceFeedbackArtifactStore"]
