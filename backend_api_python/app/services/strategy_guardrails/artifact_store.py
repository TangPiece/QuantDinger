"""Phase 8G：Strategy Guardrails R2 / 本地 JSON 工件。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import (
    GovernanceDecision,
    GovernanceEvent,
    GovernanceIncident,
    GuardrailRollbackRecord,
    StrategyRuntimeState,
)


class StrategyGuardrailsArtifactStore:
    """``qd/registry/strategy_guardrails/{strategy_code}/runtime|incidents|...``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def _write_local(self, key: str, payload: dict[str, Any]) -> tuple[str, str]:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/strategy_guardrails/", 1)[-1]
            fp = self.root / "registry" / "strategy_guardrails" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def write_runtime(self, state: StrategyRuntimeState) -> tuple[str, str]:
        key = rd_paths.strategy_guardrails_runtime_key(
            strategy_code=state.strategy_code,
        )
        return self._write_local(key, state.model_dump(mode="json"))

    def write_incident(self, incident: GovernanceIncident) -> tuple[str, str]:
        key = rd_paths.strategy_guardrails_incident_key(
            strategy_code=incident.strategy_code,
            incident_id=incident.incident_id,
        )
        return self._write_local(key, incident.model_dump(mode="json"))

    def write_decision(self, decision: GovernanceDecision) -> tuple[str, str]:
        key = rd_paths.strategy_guardrails_decision_key(
            strategy_code=decision.strategy_code,
            decision_id=decision.decision_id,
        )
        return self._write_local(key, decision.model_dump(mode="json"))

    def write_event(self, event: GovernanceEvent) -> tuple[str, str]:
        key = rd_paths.strategy_guardrails_event_key(
            strategy_code=event.strategy_code,
            event_id=event.event_id,
        )
        return self._write_local(key, event.model_dump(mode="json"))

    def write_rollback(self, record: GuardrailRollbackRecord) -> tuple[str, str]:
        key = rd_paths.strategy_guardrails_rollback_key(
            strategy_code=record.strategy_code,
            rollback_id=record.rollback_id,
        )
        return self._write_local(key, record.model_dump(mode="json"))


__all__ = ["StrategyGuardrailsArtifactStore"]
