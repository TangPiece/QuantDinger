"""dataset_hash：研究实验复现指纹（对齐 docs/data/phase1/05_contracts.md）。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """稳定序列化，保证同语义对象得到相同 hash 输入。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_dataset_hash(
    *,
    dataset_definition: dict[str, Any],
    dataset_version: str,
    snapshot_id: str,
    schema_version: str,
    processor_version: str,
    materializer_version: str,
    price_policy: dict[str, Any],
) -> str:
    """计算 dataset_hash；price_policy 必须参与，避免复权政策漂移共用缓存键。"""
    payload = "|".join(
        [
            canonical_json(dataset_definition),
            str(dataset_version),
            str(snapshot_id),
            str(schema_version),
            str(processor_version),
            str(materializer_version),
            canonical_json(price_policy),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
