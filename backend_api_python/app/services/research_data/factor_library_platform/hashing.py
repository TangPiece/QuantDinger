"""Collection / Portfolio / Cluster 内容 hash。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha256_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_collection_hash(
    *,
    member_refs: list[str],
    version: str,
) -> str:
    return _sha256_payload(
        {
            "kind": "factor_collection",
            "member_refs": sorted(member_refs),
            "version": version,
        }
    )


def compute_portfolio_spec_hash(
    *,
    member_refs: list[str],
    collection_id: str,
    weight_method: str,
    weights: dict[str, float],
    version: str,
) -> str:
    return _sha256_payload(
        {
            "kind": "factor_portfolio_spec",
            "collection_id": collection_id,
            "member_refs": sorted(member_refs),
            "weight_method": weight_method,
            "weights": {k: weights[k] for k in sorted(weights)},
            "version": version,
        }
    )


def compute_cluster_hash(
    *,
    member_refs: list[str],
    method: str,
    threshold: float,
    dataset_hash: str,
    policy_version: str,
) -> str:
    return _sha256_payload(
        {
            "kind": "factor_cluster",
            "member_refs": sorted(member_refs),
            "method": method,
            "threshold": threshold,
            "dataset_hash": dataset_hash,
            "policy_version": policy_version,
        }
    )


__all__ = [
    "compute_cluster_hash",
    "compute_collection_hash",
    "compute_portfolio_spec_hash",
]
