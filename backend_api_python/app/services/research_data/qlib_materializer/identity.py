"""Materialization identity：dataset_hash + materializer_version → materialization_id。"""

from __future__ import annotations

import hashlib

# Domain dataset_hash 仍用 materializer_version="none"；此处是派生层版本
MATERIALIZER_VERSION = "qlib_materializer@1"


def compute_materialization_id(
    dataset_hash: str,
    *,
    materializer_version: str = MATERIALIZER_VERSION,
) -> str:
    """计算派生缓存键；materializer 升级必须换目录。"""
    payload = f"{dataset_hash}|{materializer_version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
