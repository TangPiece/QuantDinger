"""Production Runtime 本地产物（manifest / events / runs）。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ArtifactRecord
from app.services.research_data.paths import (
    production_runtime_manifest_key,
    production_runtime_run_key,
)

from .protocol import ENGINE_VERSION, RuntimeInstance, RuntimeManifest, RuntimeTickResult


def runtime_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "production" / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ProductionRuntimeArtifactStore:
    """写 runtime manifest / run inference 指针。"""

    root: Path | None = None

    def dir_for(self, runtime_id: str) -> Path:
        return runtime_root(self.root) / runtime_id

    def write_manifest(self, instance: RuntimeInstance) -> ArtifactRecord:
        dest = self.dir_for(instance.runtime_id)
        dest.mkdir(parents=True, exist_ok=True)
        man = RuntimeManifest(
            runtime_id=instance.runtime_id,
            bundle_hash=instance.bundle_hash,
            engine_version=ENGINE_VERSION,
            storage_uri=str(dest),
            metadata={
                "environment": instance.environment,
                "market": instance.market,
                "strategy_code": instance.strategy_code,
            },
        )
        text = json.dumps(man.model_dump(mode="json"), ensure_ascii=False, indent=2)
        path = dest / "manifest.json"
        path.write_text(text, encoding="utf-8")
        checksum = _sha256_text(text)
        (dest / "checksums.json").write_text(
            json.dumps({"manifest.json": checksum}, indent=2), encoding="utf-8"
        )
        man = man.model_copy(update={"checksum": checksum})
        path.write_text(
            json.dumps(man.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return ArtifactRecord(
            artifact_id=f"runtime_{instance.runtime_id[:16]}",
            artifact_type="production_runtime",
            storage_uri=str(dest),
            checksum=checksum,
            metadata={
                "r2_key": production_runtime_manifest_key(runtime_id=instance.runtime_id)
            },
        )

    def write_run(
        self,
        result: RuntimeTickResult,
        *,
        bridge_payload: dict[str, Any] | None = None,
    ) -> str:
        dest = self.dir_for(result.runtime_id) / "runs" / result.run_id
        dest.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": result.run_id,
            "runtime_id": result.runtime_id,
            "idempotency_key": result.idempotency_key,
            "trading_date": result.trading_date,
            "session_phase": result.session_phase,
            "status": result.status,
            "bridge_run_id": result.bridge_run_id,
            "n_signals": len(result.signals),
            "n_intents": len(result.order_intents),
            "order_intents": [i.model_dump(mode="json") for i in result.order_intents],
            "signals": [s.model_dump(mode="json") for s in result.signals],
            "targets": [t.model_dump(mode="json") for t in result.targets],
            "gate_results": [g.model_dump(mode="json") for g in result.gate_results],
            "events": list(result.events),
            "bridge": bridge_payload or {},
            "metadata": dict(result.metadata or {}),
            "engine_version": ENGINE_VERSION,
            "r2_key": production_runtime_run_key(
                runtime_id=result.runtime_id, run_id=result.run_id
            ),
        }
        path = dest / "inference.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(dest)

    def append_event_file(
        self, runtime_id: str, event: dict[str, Any]
    ) -> Path:
        dest = self.dir_for(runtime_id) / "events"
        dest.mkdir(parents=True, exist_ok=True)
        eid = str(event.get("event_id") or "evt")
        path = dest / f"{eid}.json"
        path.write_text(
            json.dumps(event, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path
