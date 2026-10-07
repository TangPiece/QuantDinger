"""Phase 8D：Registry 绑定（幂等 link，不改 version 内容）。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from .bridge_from_candidate import PromotionEvidenceContext


def bind_registry_version(
    registry: ResearchRegistry,
    ctx: PromotionEvidenceContext,
    *,
    strategy_registry: Any,
) -> dict[str, str]:
    """确认 Registry version 存在并 link governance；不 mutate version。"""
    ver = strategy_registry.get_version(ctx.strategy_code, ctx.strategy_version)
    if hasattr(strategy_registry, "link_governance_active"):
        strategy_registry.link_governance_active(ctx.strategy_code, ctx.strategy_version)
    return {
        "version_id": str(getattr(ver, "version_id", "") or ctx.version_id),
        "content_hash": str(getattr(ver, "content_hash", "") or ctx.registry_content_hash),
        "strategy_code": ctx.strategy_code,
        "strategy_version": ctx.strategy_version,
    }


__all__ = ["bind_registry_version"]
