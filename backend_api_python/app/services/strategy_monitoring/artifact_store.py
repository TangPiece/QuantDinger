"""Phase 8F：Strategy Monitoring R2 / 本地 JSON 工件。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import MonitoringMetric, StrategyAlert, StrategyHealth


class StrategyMonitoringArtifactStore:
    """``qd/registry/strategy_monitoring/{strategy_code}/health|metrics|alerts/{id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def _write_local(self, key: str, payload: dict[str, Any]) -> tuple[str, str]:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/strategy_monitoring/", 1)[-1]
            fp = self.root / "registry" / "strategy_monitoring" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def write_health(self, health: StrategyHealth) -> tuple[str, str]:
        key = rd_paths.strategy_monitoring_health_key(
            strategy_code=health.strategy_code,
            snapshot_id=health.snapshot_id,
        )
        return self._write_local(key, health.model_dump(mode="json"))

    def write_metric(self, metric: MonitoringMetric) -> tuple[str, str]:
        key = rd_paths.strategy_monitoring_metric_key(
            strategy_code=metric.strategy_code,
            metric_id=metric.metric_id,
        )
        return self._write_local(key, metric.model_dump(mode="json"))

    def write_alert(self, alert: StrategyAlert) -> tuple[str, str]:
        key = rd_paths.strategy_monitoring_alert_key(
            strategy_code=alert.strategy_code,
            alert_id=alert.alert_id,
        )
        return self._write_local(key, alert.model_dump(mode="json"))


__all__ = ["StrategyMonitoringArtifactStore"]
