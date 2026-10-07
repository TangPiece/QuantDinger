"""Phase 8A：按 code / hash / bundle / version 解析唯一 StrategyVersionRecord。"""

from __future__ import annotations

from typing import Iterable

from .identity import normalize_strategy_code
from .protocol import StrategyVersionRecord


class ResolveAmbiguousError(LookupError):
    """解析命中多条版本。"""


class ResolveNotFoundError(LookupError):
    """无匹配版本。"""


def resolve_version(
    versions: Iterable[StrategyVersionRecord],
    *,
    strategy_code: str | None = None,
    strategy_hash: str | None = None,
    bundle_hash: str | None = None,
    version: str | None = None,
    active_version: str | None = None,
) -> StrategyVersionRecord:
    """在候选集合中解析唯一版本（8A 门面委托）。"""
    pool = list(versions)
    if strategy_code:
        code = normalize_strategy_code(strategy_code)
        pool = [v for v in pool if v.strategy_code == code]
    if version:
        label = str(version).strip()
        pool = [v for v in pool if v.strategy_version == label]
    if active_version:
        label = str(active_version).strip()
        pool = [v for v in pool if v.strategy_version == label]
    if strategy_hash:
        sh = str(strategy_hash).strip()
        pool = [v for v in pool if v.strategy_hash == sh]
    if bundle_hash:
        bh = str(bundle_hash).strip()
        pool = [v for v in pool if v.bundle_hash == bh]

    if not pool:
        raise ResolveNotFoundError("no strategy version matched")
    if len(pool) > 1:
        raise ResolveAmbiguousError(
            f"ambiguous resolve: {len(pool)} matches; narrow with version or hash"
        )
    return pool[0]
