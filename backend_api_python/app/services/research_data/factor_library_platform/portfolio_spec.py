"""FactorPortfolioSpec 组装。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from .hashing import compute_portfolio_spec_hash
from .identity import new_portfolio_id
from .protocol import ENGINE_VERSION, FactorPortfolioSpec, WeightMethod
from .weights import resolve_portfolio_weights


def build_portfolio_spec(
    *,
    member_refs: list[str],
    weight_method: WeightMethod,
    collection_id: str = "",
    name: str = "",
    version: str = "1.0.0",
    portfolio_id: str | None = None,
    metrics: Mapping[str, Mapping[str, float]] | None = None,
    corr_matrix: Mapping[str, Mapping[str, float]] | None = None,
    metadata: dict | None = None,
    published_at: datetime | None = None,
) -> FactorPortfolioSpec:
    refs = sorted(set(member_refs))
    weights = resolve_portfolio_weights(
        refs,
        method=weight_method,
        metrics=metrics,
        corr_matrix=corr_matrix,
    )
    ts = published_at or datetime.now(timezone.utc)
    ph = compute_portfolio_spec_hash(
        member_refs=refs,
        collection_id=collection_id,
        weight_method=weight_method,
        weights=weights,
        version=version,
    )
    return FactorPortfolioSpec(
        engine_version=ENGINE_VERSION,
        portfolio_id=portfolio_id or new_portfolio_id(),
        name=name,
        version=version,
        portfolio_spec_hash=ph,
        collection_id=collection_id,
        member_refs=refs,
        weight_method=weight_method,
        resolved_weights=weights,
        published_at=ts,
        metadata=dict(metadata or {}),
    )


__all__ = ["build_portfolio_spec"]
