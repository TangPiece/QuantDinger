"""Reproducibility content hashes。"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from app.services.research_data.hashing import canonical_json


def sha256_payload(payload: Mapping[str, Any] | list[Any] | dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_dependency_lock_hash(lock: Mapping[str, Any] | None) -> str:
    return sha256_payload(dict(lock or {}))


def compute_environment_hash(fingerprint: Mapping[str, Any]) -> str:
    # exclude self-referential hashes
    payload = {
        k: v
        for k, v in dict(fingerprint).items()
        if k not in ("environment_hash", "schema_version", "metadata")
    }
    return sha256_payload(payload)


def compute_input_manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = {
        k: v
        for k, v in dict(manifest).items()
        if k not in ("input_manifest_hash", "schema_version", "metadata")
    }
    return sha256_payload(payload)


__all__ = [
    "compute_dependency_lock_hash",
    "compute_environment_hash",
    "compute_input_manifest_hash",
    "sha256_payload",
]
