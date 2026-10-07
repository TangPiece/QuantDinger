"""钉住 LibraryEntry 字段。"""

from __future__ import annotations

from datetime import datetime, timezone

from .identity import new_entry_id
from .protocol import ENGINE_VERSION, FactorCategory, FactorLibraryEntry, LibraryLifecycle


def pin_library_entry(
    *,
    factor_ref: str,
    factor_hash: str,
    evaluation_id: str,
    dataset_ref: str = "",
    dataset_hash: str = "",
    lifecycle: LibraryLifecycle = "APPROVED",
    category: FactorCategory = "OTHER",
    tags: list[str] | None = None,
    quality_total: float = 0.0,
    ic_score: float = 0.0,
    icir_score: float = 0.0,
    candidate_id: str = "",
    mining_run_id: str = "",
    multiple_testing_warning: str = "",
    parent_factor_refs: list[str] | None = None,
    metadata: dict | None = None,
    entry_id: str | None = None,
    published_at: datetime | None = None,
) -> FactorLibraryEntry:
    ts = published_at or datetime.now(timezone.utc)
    return FactorLibraryEntry(
        engine_version=ENGINE_VERSION,
        entry_id=entry_id or new_entry_id(),
        factor_ref=factor_ref,
        factor_hash=factor_hash,
        evaluation_id=evaluation_id,
        dataset_ref=dataset_ref,
        dataset_hash=dataset_hash,
        lifecycle=lifecycle,
        category=category,
        tags=list(tags or []),
        quality_total=quality_total,
        ic_score=ic_score,
        icir_score=icir_score,
        candidate_id=candidate_id,
        mining_run_id=mining_run_id,
        multiple_testing_warning=multiple_testing_warning,
        parent_factor_refs=list(parent_factor_refs or []),
        published_at=ts,
        metadata=dict(metadata or {}),
    )


__all__ = ["pin_library_entry"]
