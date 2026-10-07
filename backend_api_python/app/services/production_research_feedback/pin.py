"""Phase 8H：RealitySnapshot content_hash 钉扎。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .protocol import ProductionRealitySnapshot


def snapshot_content_hash(
    *,
    strategy_code: str,
    reality_kind: str,
    as_of_time: str,
    pnl_total: float,
    metrics: Mapping[str, float],
    dataset_id: str,
    snapshot_version: int,
) -> str:
    payload: dict[str, Any] = {
        "strategy_code": str(strategy_code or "").strip(),
        "reality_kind": str(reality_kind or "").strip().upper(),
        "as_of_time": str(as_of_time or "").strip(),
        "pnl_total": float(pnl_total),
        "metrics": {k: float(v) for k, v in sorted(metrics.items())},
        "dataset_id": str(dataset_id or "").strip(),
        "snapshot_version": int(snapshot_version),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def hash_reality_snapshot(record: ProductionRealitySnapshot) -> str:
    return snapshot_content_hash(
        strategy_code=record.strategy_code,
        reality_kind=record.reality_kind,
        as_of_time=record.as_of_time,
        pnl_total=record.pnl_summary.pnl_total,
        metrics=record.metrics,
        dataset_id=record.dataset_id,
        snapshot_version=record.snapshot_version,
    )


__all__ = ["hash_reality_snapshot", "snapshot_content_hash"]
