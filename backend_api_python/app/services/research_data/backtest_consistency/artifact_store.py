"""Consistency artifact：manifest / summary / diff parquet。"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ArtifactRecord, ConsistencyRunRecord

from .models import ConsistencyReport
from .version import CONSISTENCY_ENGINE_VERSION


def consistency_artifact_root(root: Path | None = None) -> Path:
    """{research_cache}/qd/artifacts/consistency。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "artifacts" / "consistency"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_run_id(semantic_fingerprint: str, level: str) -> str:
    """内容寻址 run_id。"""
    payload = f"{semantic_fingerprint}|{level}|{CONSISTENCY_ENGINE_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _df_parquet_bytes(df: pd.DataFrame) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


@dataclass
class ConsistencyArtifactStore:
    """写入 consistency 报告与差分表。"""

    root: Path | None = None

    def dir_for(self, run_id: str) -> Path:
        return consistency_artifact_root(self.root) / run_id

    def write_report(self, report: ConsistencyReport) -> ArtifactRecord:
        """落盘并回写 report.artifact_uris。"""
        dest = self.dir_for(report.run_id)
        dest.mkdir(parents=True, exist_ok=True)
        uris: dict[str, str] = {}
        blobs: list[bytes] = []

        summary = {
            "run_id": report.run_id,
            "dataset_hash": report.dataset_hash,
            "signal_artifact_id": report.signal_artifact_id,
            "semantic_fingerprint": report.semantic_fingerprint,
            "level": report.level,
            "qlib_result_id": report.qlib_result_id,
            "qd_result_id": report.qd_result_id,
            "status": report.status,
            "max_equity_diff": report.max_equity_diff,
            "max_position_diff": report.max_position_diff,
            "engine_version": report.engine_version or CONSISTENCY_ENGINE_VERSION,
            "n_diffs": len(report.diffs),
            "attribution": [a.model_dump(mode="json") for a in report.attribution],
        }
        sum_text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
        sum_path = dest / "summary.json"
        sum_path.write_text(sum_text, encoding="utf-8")
        uris["summary"] = str(sum_path.resolve())
        blobs.append(sum_text.encode("utf-8"))

        def _write_dim(name: str, rows: list[dict[str, Any]]) -> None:
            if not rows:
                return
            raw = _df_parquet_bytes(pd.DataFrame(rows))
            path = dest / f"{name}.parquet"
            path.write_bytes(raw)
            uris[name] = str(path.resolve())
            blobs.append(raw)

        by_dim: dict[str, list[dict]] = {
            "equity_diff": [],
            "position_diff": [],
            "trade_diff": [],
            "cost_diff": [],
        }
        for d in report.diffs:
            row = d.model_dump(mode="json")
            if d.dimension == "equity":
                by_dim["equity_diff"].append(row)
            elif d.dimension == "position":
                by_dim["position_diff"].append(row)
            elif d.dimension == "trade":
                by_dim["trade_diff"].append(row)
            elif d.dimension in ("cost", "cash", "rejected"):
                by_dim["cost_diff"].append(row)
        for name, rows in by_dim.items():
            _write_dim(name, rows)

        if report.attribution:
            attr_bytes = _df_parquet_bytes(
                pd.DataFrame([a.model_dump(mode="json") for a in report.attribution])
            )
            attr_path = dest / "attribution.parquet"
            attr_path.write_bytes(attr_bytes)
            uris["attribution"] = str(attr_path.resolve())
            blobs.append(attr_bytes)

        checksum = hashlib.sha256(b"".join(blobs)).hexdigest()
        manifest = {
            "run_id": report.run_id,
            "engine_version": CONSISTENCY_ENGINE_VERSION,
            "level": report.level,
            "dataset_hash": report.dataset_hash,
            "semantic_fingerprint": report.semantic_fingerprint,
            "status": report.status,
            "artifacts": list(uris.keys()),
            "checksum": checksum,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        man_text = json.dumps(manifest, ensure_ascii=False, indent=2, default=str)
        man_path = dest / "manifest.json"
        man_path.write_text(man_text, encoding="utf-8")
        uris["manifest"] = str(man_path.resolve())

        report.artifact_uris = uris
        return ArtifactRecord(
            artifact_id=report.run_id,
            artifact_type="consistency",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=sum(len(b) for b in blobs) + len(man_text.encode("utf-8")),
            metadata={
                "dataset_hash": report.dataset_hash,
                "qlib_result_id": report.qlib_result_id,
                "qd_result_id": report.qd_result_id,
                "status": report.status,
                "max_equity_diff": report.max_equity_diff,
                "max_position_diff": report.max_position_diff,
                "level": report.level,
                "semantic_fingerprint": report.semantic_fingerprint,
                "created_at": manifest["created_at"],
            },
        )


def report_to_run_record(report: ConsistencyReport) -> ConsistencyRunRecord:
    """Report → Registry ConsistencyRunRecord。"""
    return ConsistencyRunRecord(
        run_id=report.run_id,
        dataset_hash=report.dataset_hash,
        qlib_result_id=report.qlib_result_id,
        qd_result_id=report.qd_result_id,
        status=report.status,
        max_equity_diff=report.max_equity_diff,
        max_position_diff=report.max_position_diff,
        artifact_uri=report.artifact_uris.get("manifest", ""),
        level=report.level,
        semantic_fingerprint=report.semantic_fingerprint,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata=dict(report.metadata or {}),
    )
