"""Materialization manifest.json 读写。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .identity import MATERIALIZER_VERSION
from .protocol import MaterializationStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def build_manifest(
    *,
    dataset_code: str,
    dataset_version: str,
    dataset_hash: str,
    snapshot_id: str,
    schema_version: str,
    price_policy: dict[str, Any],
    processor: str | None,
    materialization_id: str,
    qlib_version: str,
    calendar_min: str | None,
    calendar_max: str | None,
    calendar_count: int,
    instrument_count: int,
    features: list[str],
    checksum: str,
    status: MaterializationStatus = MaterializationStatus.READY,
    row_count: int = 0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装 manifest 语义内容。"""
    payload: dict[str, Any] = {
        "dataset_code": dataset_code,
        "dataset_version": dataset_version,
        "dataset_hash": dataset_hash,
        "snapshot_id": snapshot_id,
        "schema_version": schema_version,
        "price_policy": price_policy,
        "processor": processor or "",
        "materializer_version": MATERIALIZER_VERSION,
        "materialization_id": materialization_id,
        "qlib_version": qlib_version,
        "created_at": _utc_now().isoformat().replace("+00:00", "Z"),
        "status": status.value,
        "calendar": {
            "min": calendar_min,
            "max": calendar_max,
            "count": calendar_count,
        },
        "instruments": {"count": instrument_count},
        "features": features,
        "row_count": row_count,
        "checksum": checksum,
        "checksums": {"tree": checksum},
    }
    if extra:
        payload["extra"] = extra
    return payload


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def detect_qlib_version() -> str:
    """读取已安装 qlib 版本；未安装则标记 unknown（写盘仍可进行）。"""
    try:
        import qlib

        return str(getattr(qlib, "__version__", "unknown"))
    except Exception:
        return "unavailable"
