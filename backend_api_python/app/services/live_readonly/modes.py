"""Phase 7A/7C：TradingEnvironment 阶梯；禁止 PAPER→LIVE 等跳跃。"""

from __future__ import annotations

from typing import Optional

from .protocol import TradingEnvironment

# Phase 7 允许的环境（不含 LIVE）
_ALLOWED_PHASE7: frozenset[str] = frozenset(
    {"PAPER", "SHADOW", "LIVE_READONLY", "LIVE_CONTROLLED"}
)

# 合法单步前进边（LIVE_CONTROLLED→LIVE 仅 governance 授权时开放，见 assert_transition）
_TRANSITIONS: dict[str, frozenset[str]] = {
    "PAPER": frozenset({"SHADOW"}),
    "SHADOW": frozenset({"LIVE_READONLY"}),
    "LIVE_READONLY": frozenset({"LIVE_CONTROLLED"}),
    "LIVE_CONTROLLED": frozenset({"LIVE"}),
    "LIVE": frozenset(),
}


class EnvironmentTransitionError(RuntimeError):
    """非法环境转换。"""


def normalize_environment(
    env: str,
    *,
    governance_live_authorized: bool = False,
) -> TradingEnvironment:
    """规范化环境名；LIVE 默认禁止， governance 授权后可解析。"""
    e = str(env or "PAPER").strip().upper()
    if e == "LIVE" and not governance_live_authorized:
        raise EnvironmentTransitionError("LIVE forbidden without governance authorization")
    if e not in (
        "PAPER",
        "SHADOW",
        "LIVE_READONLY",
        "LIVE_CONTROLLED",
        "LIVE",
    ):
        raise EnvironmentTransitionError(f"unsupported environment: {env!r}")
    return e  # type: ignore[return-value]


def assert_transition(
    from_env: str,
    to_env: str,
    *,
    production_ready: bool = False,
    governance_live_authorized: bool = False,
) -> TradingEnvironment:
    """校验环境阶梯；PAPER→LIVE 等跳跃一律拒绝。"""
    src = normalize_environment(from_env)
    dst_raw = str(to_env or "PAPER").strip().upper()
    dst = normalize_environment(
        to_env, governance_live_authorized=governance_live_authorized
    )

    if src == dst:
        return dst

    # LIVE 仅 LIVE_CONTROLLED + governance 双重门禁
    if dst_raw == "LIVE" and not governance_live_authorized:
        raise EnvironmentTransitionError("LIVE forbidden without governance authorization")

    # 硬禁：PAPER 不能直接到 LIVE_READONLY / LIVE_CONTROLLED
    if src == "PAPER" and dst in ("LIVE_READONLY", "LIVE_CONTROLLED", "LIVE"):
        raise EnvironmentTransitionError(f"transition {src}→{dst} forbidden")

    allowed = _TRANSITIONS.get(src, frozenset())
    if dst not in allowed:
        raise EnvironmentTransitionError(
            f"transition {src}→{dst} not allowed (allowed: {sorted(allowed)})"
        )

    if dst in ("LIVE_READONLY", "LIVE_CONTROLLED") and not production_ready:
        raise EnvironmentTransitionError(
            f"→{dst} requires PRODUCTION_READY=true"
        )

    return dst


def current_allowed_targets(from_env: str) -> tuple[str, ...]:
    """返回当前环境下可转换目标（调试/文档用）。"""
    src = str(from_env or "PAPER").strip().upper()
    return tuple(sorted(_TRANSITIONS.get(src, frozenset()) & _ALLOWED_PHASE7))
