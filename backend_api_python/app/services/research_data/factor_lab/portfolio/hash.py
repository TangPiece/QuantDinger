"""portfolio_hash：钉住 factor/evaluation + 组合规格。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import PortfolioSpec


def normalize_portfolio_spec(
    spec: PortfolioSpec, *, factor_dataset_hash: str
) -> dict:
    """规范化 hash 输入。"""
    return {
        "factor_dataset_id": spec.factor_dataset_id,
        "factor_dataset_hash": factor_dataset_hash,
        "evaluation_hash": spec.evaluation_hash,
        "construction_method": spec.construction_method,
        "weight_method": spec.weight_method,
        "selection_mode": spec.selection_mode,
        "top_n": spec.top_n,
        "top_pct": float(spec.top_pct) if spec.top_pct is not None else None,
        "group_count": int(spec.group_count),
        "rebalance_frequency": spec.rebalance_frequency,
        "horizon": int(spec.horizon),
        "min_turnover": float(spec.min_turnover),
        "min_cross_section_size": int(spec.min_cross_section_size),
        "direction": spec.direction,
        "portfolio_version": spec.portfolio_version,
    }


def compute_portfolio_hash(
    spec: PortfolioSpec, *, factor_dataset_hash: str
) -> str:
    """稳定 portfolio_hash。"""
    payload = normalize_portfolio_spec(spec, factor_dataset_hash=factor_dataset_hash)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
