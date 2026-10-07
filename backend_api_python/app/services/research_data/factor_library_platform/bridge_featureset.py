"""导出 9B FeatureSetDefinition。"""

from __future__ import annotations

from app.services.research_data.feature_factor_platform.feature_set import FeatureSetDefinition

from .protocol import FactorCollection, FactorPortfolioSpec


def to_feature_set_definition(
    *,
    code: str,
    version: str,
    member_refs: list[str],
    name: str = "",
    metadata: dict | None = None,
) -> FeatureSetDefinition:
    return FeatureSetDefinition(
        code=code,
        version=version,
        name=name,
        member_refs=sorted(set(member_refs)),
        metadata=dict(metadata or {}),
    )


def from_collection(coll: FactorCollection, *, code: str, version: str) -> FeatureSetDefinition:
    return to_feature_set_definition(
        code=code,
        version=version,
        member_refs=list(coll.member_refs),
        name=coll.name,
        metadata={"collection_id": coll.collection_id, "collection_hash": coll.collection_hash},
    )


def from_portfolio(spec: FactorPortfolioSpec, *, code: str, version: str) -> FeatureSetDefinition:
    meta = {
        "portfolio_id": spec.portfolio_id,
        "portfolio_spec_hash": spec.portfolio_spec_hash,
        "weight_method": spec.weight_method,
        "weights": dict(spec.resolved_weights),
    }
    return to_feature_set_definition(
        code=code,
        version=version,
        member_refs=list(spec.member_refs),
        name=spec.name,
        metadata=meta,
    )


__all__ = ["from_collection", "from_portfolio", "to_feature_set_definition"]
