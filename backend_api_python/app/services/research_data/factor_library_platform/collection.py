"""FactorCollection 组装。"""

from __future__ import annotations

from datetime import datetime, timezone

from .hashing import compute_collection_hash
from .identity import new_collection_id
from .protocol import ENGINE_VERSION, FactorCollection


def build_collection(
    *,
    member_refs: list[str],
    name: str = "",
    version: str = "1.0.0",
    collection_id: str | None = None,
    metadata: dict | None = None,
    published_at: datetime | None = None,
) -> FactorCollection:
    refs = sorted(set(member_refs))
    ts = published_at or datetime.now(timezone.utc)
    ch = compute_collection_hash(member_refs=refs, version=version)
    return FactorCollection(
        engine_version=ENGINE_VERSION,
        collection_id=collection_id or new_collection_id(),
        name=name,
        version=version,
        collection_hash=ch,
        member_refs=refs,
        published_at=ts,
        metadata=dict(metadata or {}),
    )


__all__ = ["build_collection"]
