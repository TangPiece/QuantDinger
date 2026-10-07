"""Phase 8H：ProductionFeedbackDataset dataset_hash（定义 + schema + filter + window + processor）。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from app.services.research_data.hashing import canonical_json

from .protocol import FeedbackRow, ProductionFeedbackDataset


def compute_feedback_dataset_hash(
    *,
    strategy_code: str,
    feedback_type: str,
    schema_version: str,
    filter_spec: Mapping[str, Any],
    window_start: str,
    window_end: str,
    processor_id: str,
    processor_version: str,
    rows: list[FeedbackRow] | list[Mapping[str, Any]],
) -> str:
    row_payload = [
        r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r) for r in rows
    ]
    definition = {
        "strategy_code": str(strategy_code or "").strip(),
        "feedback_type": str(feedback_type or "").strip().upper(),
        "rows": row_payload,
    }
    payload = "|".join(
        [
            canonical_json(definition),
            str(schema_version),
            canonical_json(dict(filter_spec)),
            str(window_start),
            str(window_end),
            str(processor_id),
            str(processor_version),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_feedback_dataset(record: ProductionFeedbackDataset) -> str:
    return compute_feedback_dataset_hash(
        strategy_code=record.strategy_code,
        feedback_type=record.feedback_type,
        schema_version=record.schema_version,
        filter_spec=record.filter_spec,
        window_start=record.window_start,
        window_end=record.window_end,
        processor_id=record.processor_id,
        processor_version=record.processor_version,
        rows=record.rows,
    )


__all__ = ["compute_feedback_dataset_hash", "hash_feedback_dataset"]
