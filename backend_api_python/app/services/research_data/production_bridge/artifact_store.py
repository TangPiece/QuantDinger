"""Production Bundle / Run 本地产物。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    ProductionBundleSummary,
)
from app.services.research_data.paths import (
    production_bundle_manifest_key,
    production_bundle_summary_key,
    production_run_prefix,
)

from .integrity import sha256_text
from .protocol import (
    BundleManifest,
    ENGINE_VERSION,
    FeatureParityReport,
    InferenceResponse,
)


def bundle_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "production" / "bundles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "production" / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ProductionBundleArtifactStore:
    """写 bundle / run 产物。"""

    root: Path | None = None

    def dir_for(self, bundle_hash: str) -> Path:
        return bundle_root(self.root) / bundle_hash

    def write_bundle(
        self,
        manifest: BundleManifest,
        *,
        summary: ProductionBundleSummary,
        strategy_snapshot: dict[str, Any] | None = None,
        execution_policy: dict[str, Any] | None = None,
        dependency_lock: dict[str, Any] | None = None,
        processor: dict[str, Any] | None = None,
        model_pointer: dict[str, Any] | None = None,
        parity: FeatureParityReport | None = None,
    ) -> ArtifactRecord:
        bh = manifest.bundle_hash
        dest = self.dir_for(bh)
        dest.mkdir(parents=True, exist_ok=True)
        checksums: dict[str, str] = {}

        def _write(rel: str, payload: Any) -> None:
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            path.write_text(text, encoding="utf-8")
            checksums[rel] = sha256_text(text)

        _write(
            "summary.json",
            {
                "bundle_hash": bh,
                "engine_version": ENGINE_VERSION,
                "summary": summary.model_dump(mode="json"),
                "r2_key": production_bundle_summary_key(bundle_hash=bh),
            },
        )
        _write(
            "strategy/snapshot.json",
            strategy_snapshot
            or {
                "strategy_hash": summary.strategy_hash,
                "strategy_code": summary.strategy_code,
                "signal_definition_json": (summary.metadata or {}).get(
                    "signal_definition_json"
                ),
                "rebalance_rule_json": (summary.metadata or {}).get(
                    "rebalance_rule_json"
                ),
                "holding_rule_json": (summary.metadata or {}).get("holding_rule_json"),
            },
        )
        _write(
            "config/execution_policy.json",
            execution_policy
            or {
                "execution_policy": summary.execution_policy,
                "realism": summary.realism,
                "market_rule": summary.market_rule,
            },
        )
        _write(
            "dependency/lock.json",
            dependency_lock or summary.dependency_lock_json or {},
        )
        if processor is not None:
            _write("processor/pipeline.json", processor)
        if model_pointer is not None:
            _write("model/pointer.json", model_pointer)
        if parity is not None:
            _write("feature/parity_report.json", parity.model_dump(mode="json"))

        _write("checksums.json", checksums)
        man_payload = manifest.model_dump(mode="json")
        man_payload["file_checksums"] = checksums
        man_payload.setdefault(
            "r2_key", production_bundle_manifest_key(bundle_hash=bh)
        )
        man_text = json.dumps(man_payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(man_text, encoding="utf-8")
        checksum = hashlib.sha256(man_text.encode("utf-8")).hexdigest()

        return ArtifactRecord(
            artifact_id=bh,
            artifact_type="production_bundle",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(man_text.encode("utf-8")),
            metadata={
                "bundle_hash": bh,
                "strategy_hash": summary.strategy_hash,
                "status": summary.status,
            },
        )

    def write_run(self, response: InferenceResponse) -> str:
        """写干跑 run 产物；返回 storage_uri。"""
        rid = response.run_id
        dest = run_root(self.root) / rid
        dest.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": rid,
            "response": response.model_dump(mode="json"),
            "r2_key": production_run_prefix(run_id=rid),
        }
        (dest / "inference.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(dest.resolve())
