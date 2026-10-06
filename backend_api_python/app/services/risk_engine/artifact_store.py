"""Risk 本地产物。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.paths import (
    production_risk_decision_key,
    production_risk_snapshot_key,
)

from .protocol import ENGINE_VERSION, RiskDecision, RiskEvaluateResult, RiskSnapshot


def risk_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "production" / "risk"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class RiskArtifactStore:
    root: Path | None = None

    def dir_for(self, risk_run_id: str) -> Path:
        dest = risk_root(self.root) / risk_run_id
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def write_run(
        self,
        result: RiskEvaluateResult,
        *,
        decision: RiskDecision | None = None,
        snapshot: RiskSnapshot | None = None,
    ) -> str:
        dest = self.dir_for(result.risk_run_id)
        snap = snapshot or result.snapshot
        dec = decision or result.decision
        if snap is not None:
            (dest / "snapshot.json").write_text(
                json.dumps(
                    {
                        "engine_version": ENGINE_VERSION,
                        "snapshot": snap.model_dump(mode="json"),
                        "r2_key": production_risk_snapshot_key(
                            risk_run_id=result.risk_run_id
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        if dec is not None:
            (dest / "decision.json").write_text(
                json.dumps(
                    {
                        "engine_version": ENGINE_VERSION,
                        "decision": dec.model_dump(mode="json"),
                        "order_intents": [
                            i.model_dump(mode="json") for i in result.order_intents
                        ],
                        "r2_key": production_risk_decision_key(
                            risk_run_id=result.risk_run_id
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        events_dir = dest / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        for ev in result.events:
            (events_dir / f"{ev.event_id}.json").write_text(
                json.dumps(ev.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return str(dest)
