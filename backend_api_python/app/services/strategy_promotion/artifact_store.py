"""Phase 8D：Promotion manifest（R2 / 本地）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import PromotionRunRecord


class PromotionArtifactStore:
    """``qd/registry/promotions/{pipeline_run_id}/manifest.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_manifest(self, run: PromotionRunRecord) -> tuple[str, str]:
        key = rd_paths.strategy_promotion_manifest_key(pipeline_run_id=run.pipeline_run_id)
        payload: dict[str, Any] = {
            "pipeline_run_id": run.pipeline_run_id,
            "request_id": run.request_id,
            "strategy_code": run.strategy_code,
            "from_environment": run.from_environment,
            "to_environment": run.to_environment,
            "policy_id": run.policy_id,
            "policy_version": run.policy_version,
            "policy_content_hash": run.policy_content_hash,
            "status": run.status,
            "stages": [s.model_dump(mode="json") for s in run.stages],
            "session_id": run.session_id,
            "governance_state": run.governance_state,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/promotions/", 1)[-1]
            fp = self.root / "registry" / "promotions" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs


__all__ = ["PromotionArtifactStore"]
