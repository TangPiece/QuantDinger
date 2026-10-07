"""Library entry / collection / portfolio 引用与 R2 键。"""

from __future__ import annotations

import uuid

from app.services.research_data import config as rd_config


def new_entry_id() -> str:
    return f"lib_{uuid.uuid4().hex[:16]}"


def new_collection_id() -> str:
    return f"fcoll_{uuid.uuid4().hex[:16]}"


def new_portfolio_id() -> str:
    return f"fport_{uuid.uuid4().hex[:16]}"


def new_cluster_id() -> str:
    return f"fclu_{uuid.uuid4().hex[:16]}"


def library_entry_key(*, entry_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/factor_library_platform/entries/{entry_id}.json"


def collection_key(*, collection_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/factor_library_platform/collections/{collection_id}.json"


def portfolio_spec_key(*, portfolio_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/factor_library_platform/portfolios/{portfolio_id}.json"


def cluster_key(*, cluster_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/factor_library_platform/clusters/{cluster_id}.json"


__all__ = [
    "cluster_key",
    "collection_key",
    "library_entry_key",
    "new_cluster_id",
    "new_collection_id",
    "new_entry_id",
    "new_portfolio_id",
    "portfolio_spec_key",
]
