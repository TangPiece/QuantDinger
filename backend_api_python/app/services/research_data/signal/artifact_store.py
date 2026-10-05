"""Signal Artifact 落盘：research_cache/qd/artifacts/signal/{artifact_id}/。"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    Signal,
    TargetPosition,
)
from app.services.research_data.hashing import canonical_json

from .version import SIGNAL_PIPELINE_VERSION


def compute_signal_artifact_id(
    *,
    prediction_fingerprint: str,
    strategy_digest: str,
    portfolio_digest: str,
    pipeline_version: str = SIGNAL_PIPELINE_VERSION,
) -> str:
    """内容寻址 signal artifact 键。"""
    payload = "|".join(
        [
            str(prediction_fingerprint),
            str(strategy_digest),
            str(portfolio_digest),
            str(pipeline_version),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signal_artifact_root(root: Path | None = None) -> Path:
    """{research_cache}/qd/artifacts/signal。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "artifacts" / "signal"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _signals_parquet_bytes(records: list[Signal]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "signal_id": [r.signal_id for r in records],
            "instrument_key": [r.instrument_key for r in records],
            "trading_date": [r.trading_date for r in records],
            "direction": [r.direction for r in records],
            "score": [r.score for r in records],
            "rank": [r.rank for r in records],
            "signal_time": [r.signal_time.isoformat() for r in records],
            "knowledge_time": [r.knowledge_time.isoformat() for r in records],
            "execution_time": [r.execution_time.isoformat() for r in records],
            "model_version": [r.model_version for r in records],
            "strategy_version": [r.strategy_version for r in records],
            "dataset_hash": [r.dataset_hash for r in records],
            "bundle_hash": [r.bundle_hash for r in records],
            "target_weight": [r.target_weight for r in records],
        }
    )
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


def _positions_parquet_bytes(records: list[TargetPosition]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "instrument_key": [r.instrument_key for r in records],
            "trading_date": [r.trading_date for r in records],
            "portfolio_id": [r.portfolio_id for r in records],
            "strategy_version": [r.strategy_version for r in records],
            "dataset_hash": [r.dataset_hash for r in records],
            "timestamp": [r.timestamp.isoformat() for r in records],
            "target_weight": [r.target_weight for r in records],
            "target_quantity": [r.target_quantity for r in records],
            "signal_id": [r.signal_id for r in records],
        }
    )
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


@dataclass
class SignalArtifactStore:
    """写入 signals.parquet / target_positions.parquet / metadata.json。"""

    root: Path | None = None

    def dir_for(self, artifact_id: str) -> Path:
        return signal_artifact_root(self.root) / artifact_id

    def write_bundle(
        self,
        artifact_id: str,
        *,
        signals: list[Signal],
        positions: list[TargetPosition],
        metadata: dict[str, Any],
    ) -> ArtifactRecord:
        """原子写入 signal artifact 目录。"""
        dest = self.dir_for(artifact_id)
        dest.mkdir(parents=True, exist_ok=True)
        sig_bytes = _signals_parquet_bytes(signals)
        pos_bytes = _positions_parquet_bytes(positions)
        (dest / "signals.parquet").write_bytes(sig_bytes)
        (dest / "target_positions.parquet").write_bytes(pos_bytes)
        meta_text = json.dumps(metadata, ensure_ascii=False, indent=2, default=str)
        (dest / "metadata.json").write_text(meta_text, encoding="utf-8")

        checksum = hashlib.sha256(sig_bytes + pos_bytes).hexdigest()
        size_bytes = len(sig_bytes) + len(pos_bytes)
        return ArtifactRecord(
            artifact_id=artifact_id,
            artifact_type="signal",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=size_bytes,
            metadata=metadata,
        )

    def read_metadata(self, artifact_id: str) -> dict[str, Any]:
        path = self.dir_for(artifact_id) / "metadata.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))


def strategy_config_digest(obj: Any) -> str:
    """策略/组合 digest 辅助（已有对象用自身 digest）。"""
    if hasattr(obj, "strategy_digest"):
        return str(obj.strategy_digest())
    if hasattr(obj, "portfolio_digest"):
        return str(obj.portfolio_digest())
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
