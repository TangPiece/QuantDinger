"""Phase 8C：Validation result.json（R2 / 本地）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import ValidationResult, ValidationRunRecord


class ValidationArtifactStore:
    """``qd/registry/validations/{validation_id}/result.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_result(
        self,
        run: ValidationRunRecord,
        result: ValidationResult,
    ) -> tuple[str, str]:
        """写入 result.json；返回 (storage_uri, checksum)。"""
        key = rd_paths.strategy_validation_result_key(validation_id=run.validation_id)
        payload: dict[str, Any] = {
            "validation_id": run.validation_id,
            "candidate_id": run.candidate_id,
            "policy_id": run.policy_id,
            "policy_version": run.policy_version,
            "policy_content_hash": run.policy_content_hash,
            "validator_version": run.validator_version,
            "status": run.status,
            "result": result.model_dump(mode="json"),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/validations/", 1)[-1]
            fp = self.root / "registry" / "validations" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs


__all__ = ["ValidationArtifactStore"]
