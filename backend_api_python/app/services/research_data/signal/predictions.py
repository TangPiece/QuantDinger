"""Prediction 行 id / 指纹（确定性）。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable

from app.services.research_data.contracts import PredictionRecord
from app.services.research_data.hashing import canonical_json


def compute_prediction_id(
    *,
    model_version: str,
    instrument_key: str,
    trading_date: str,
    dataset_hash: str,
) -> str:
    """单行 Prediction 确定性 id。"""
    payload = "|".join(
        [
            str(model_version),
            str(instrument_key),
            str(trading_date),
            str(dataset_hash),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_prediction(
    record: PredictionRecord,
    *,
    snapshot_id: str | None = None,
    created_at: datetime | None = None,
) -> PredictionRecord:
    """补齐 prediction_id / snapshot_id；不改变 prediction 数值语义。"""
    pid = record.prediction_id or compute_prediction_id(
        model_version=record.model_version,
        instrument_key=record.instrument_key,
        trading_date=record.trading_date,
        dataset_hash=record.dataset_hash,
    )
    snap = snapshot_id if snapshot_id is not None else record.snapshot_id
    ts = created_at if created_at is not None else record.created_at
    if ts is None:
        ts = datetime.now(timezone.utc).replace(microsecond=0)
    return record.model_copy(
        update={
            "prediction_id": pid,
            "snapshot_id": snap or "",
            "created_at": ts,
        }
    )


def normalize_predictions(
    records: Iterable[PredictionRecord],
    *,
    snapshot_id: str | None = None,
) -> list[PredictionRecord]:
    """批量规范化 PredictionRecord。"""
    return [
        normalize_prediction(r, snapshot_id=snapshot_id) for r in records
    ]


def prediction_fingerprint(records: Iterable[PredictionRecord]) -> str:
    """整批 Prediction 内容指纹（排序后 canonical）。"""
    rows = []
    for r in records:
        rows.append(
            {
                "prediction_id": r.prediction_id,
                "instrument_key": r.instrument_key,
                "trading_date": r.trading_date,
                "prediction": r.prediction,
                "model_version": r.model_version,
                "dataset_hash": r.dataset_hash,
                "bundle_hash": r.bundle_hash,
                "snapshot_id": r.snapshot_id,
            }
        )
    rows.sort(
        key=lambda x: (
            x["trading_date"],
            x["instrument_key"],
            x["prediction_id"],
        )
    )
    return hashlib.sha256(
        canonical_json(rows).encode("utf-8")
    ).hexdigest()
