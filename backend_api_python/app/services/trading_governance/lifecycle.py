"""Phase 7E：策略生命周期状态机（禁 DRAFT→LIVE 等跳跃）。"""

from __future__ import annotations

from .protocol import ScaleLevel, StrategyLifecycleState

# 合法单步前进（不含 kill→PAUSED，任意态可 PAUSED 由 kill 模块处理）
_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"VALIDATING"}),
    "VALIDATING": frozenset({"SHADOW", "DRAFT"}),
    "SHADOW": frozenset({"CONTROLLED_LIVE", "PAUSED"}),
    "CONTROLLED_LIVE": frozenset({"LIVE", "PAUSED", "STOPPED"}),
    "LIVE": frozenset({"PAUSED", "STOPPED"}),
    "PAUSED": frozenset({"SHADOW", "CONTROLLED_LIVE", "LIVE", "STOPPED", "RETIRED"}),
    "STOPPED": frozenset({"RETIRED", "SHADOW"}),
    "RETIRED": frozenset(),
}

# 禁止直达 LIVE 的源状态
_FORBIDDEN_TO_LIVE_FROM = frozenset({"DRAFT", "VALIDATING", "SHADOW"})


class LifecycleTransitionError(RuntimeError):
    """非法生命周期转换。"""


def assert_transition(
    from_state: StrategyLifecycleState,
    to_state: StrategyLifecycleState,
    *,
    scale_level: ScaleLevel = "L0_SHADOW",
    live_go_live_approved: bool = False,
) -> StrategyLifecycleState:
    """校验生命周期；进入 LIVE 须 L4 + 显式 go-live 审批。"""
    src = str(from_state).upper()
    dst = str(to_state).upper()

    if src == dst:
        return dst  # type: ignore[return-value]

    if dst == "LIVE":
        if src in _FORBIDDEN_TO_LIVE_FROM:
            raise LifecycleTransitionError(f"{src}→LIVE forbidden")
        if scale_level != "L4_PRODUCTION":
            raise LifecycleTransitionError("LIVE requires scale L4_PRODUCTION")
        if not live_go_live_approved:
            raise LifecycleTransitionError("LIVE requires STRATEGY_GO_LIVE approval")

    # kill：任意态可进入 PAUSED
    if dst == "PAUSED":
        return dst  # type: ignore[return-value]

    allowed = _TRANSITIONS.get(src, frozenset())
    if dst not in allowed:
        raise LifecycleTransitionError(
            f"transition {src}→{dst} not allowed (allowed: {sorted(allowed)})"
        )
    return dst  # type: ignore[return-value]
