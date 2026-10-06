"""Group evaluation manifest / summary.json。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    GroupEvaluationSummary,
)
from app.services.research_data.paths import (
    evaluation_groups_manifest_key,
    evaluation_groups_summary_key,
)

from .protocol import GROUP_VERSION, GroupManifest


class GroupManifestError(ValueError):
    pass


def groups_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "evaluation" / "groups"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class GroupArtifactStore:
    root: Path | None = None

    def dir_for(self, group_evaluation_hash: str) -> Path:
        return groups_root(self.root) / group_evaluation_hash

    def write_manifest(
        self,
        manifest: GroupManifest,
        *,
        summaries: list[GroupEvaluationSummary] | None = None,
    ) -> ArtifactRecord:
        ghash = manifest.group_evaluation_hash
        if not ghash:
            raise GroupManifestError("group_evaluation_hash required")
        dest = self.dir_for(ghash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", evaluation_groups_manifest_key(group_evaluation_hash=ghash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summaries is not None:
            summary_payload: dict[str, Any] = {
                "group_evaluation_hash": ghash,
                "evaluation_hash": manifest.evaluation_hash,
                "group_version": manifest.group_version or GROUP_VERSION,
                "summaries": [s.model_dump(mode="json") for s in summaries],
                "r2_key": evaluation_groups_summary_key(group_evaluation_hash=ghash),
            }
            (dest / "summary.json").write_text(
                json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=ghash,
            artifact_type="factor_group_evaluation",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "group_evaluation_hash": ghash,
                "evaluation_hash": manifest.evaluation_hash,
                "factor_dataset_id": manifest.factor_dataset_id,
            },
        )
