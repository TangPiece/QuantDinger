"""Phase 8A：Strategy Registry 版本 manifest（R2 / 本地）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import StrategyVersionRecord


class StrategyRegistryArtifactStore:
    """``qd/registry/strategies/{strategy_code}/versions/{version_id}/manifest.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_version_manifest(
        self, record: StrategyVersionRecord
    ) -> tuple[str, str]:
        """写入 manifest；返回 (storage_uri, checksum)。"""
        key = rd_paths.strategy_registry_version_manifest_key(
            strategy_code=record.strategy_code,
            version_id=record.version_id,
        )
        payload: dict[str, Any] = record.model_dump(mode="json")
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/strategies/", 1)[-1]
            fp = self.root / "registry" / "strategies" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
