"""Phase 7A：TradingEnvironment 阶梯转换；禁止 PAPER→LIVE 等跳跃。"""

from __future__ import annotations

from typing import Optional

from .protocol import TradingEnvironment

# 7A 允许的目标环境（不含 LIVE_CONTROLLED / LIVE）
_ALLOWED_7A: frozenset[str] = frozenset({"PAPER", "SHADOW", "LIVE_READONLY"})

# 合法单步前进边（7B 收紧：PAPER 仅 → SHADOW；LIVE_READONLY 需经 SHADOW + PRODUCTION_READY）
_TRANSITIONS: dict[str, frozenset[str]] = {
    "PAPER": frozenset({"SHADOW"}),
    "SHADOW": frozenset({"LIVE_READONLY"}),
    "LIVE_READONLY": frozenset(),  # 7A 禁止离开只读进入发单环境
    "LIVE_CONTROLLED": frozenset(),
    "LIVE": frozenset(),
}


class EnvironmentTransitionError(RuntimeError):
    """非法环境转换。"""


def normalize_environment(env: str) -> TradingEnvironment:
    """规范化环境名；未知值抛错。"""
    e = str(env or "PAPER").strip().upper()
    if e not in _ALLOWED_7A and e in ("LIVE_CONTROLLED", "LIVE"):
        raise EnvironmentTransitionError(
            f"{e} forbidden in Phase 7A (read-only only)"
        )
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
) -> TradingEnvironment:
    """校验环境阶梯；PAPER→LIVE 等跳跃一律拒绝。"""
    src = normalize_environment(from_env)
    dst = normalize_environment(to_env)

    if src == dst:
        return dst

    # 硬禁：任意源直接跳到 LIVE / LIVE_CONTROLLED
    if dst in ("LIVE", "LIVE_CONTROLLED"):
        raise EnvironmentTransitionError(
            f"transition {src}→{dst} forbidden in Phase 7A"
        )

    # 硬禁：PAPER 不能直接到 LIVE（normalize 已拦 LIVE；再显式防别名）
    if src == "PAPER" and dst == "LIVE":
        raise EnvironmentTransitionError("PAPER→LIVE forbidden")

    allowed = _TRANSITIONS.get(src, frozenset())
    if dst not in allowed:
        raise EnvironmentTransitionError(
            f"transition {src}→{dst} not allowed (allowed: {sorted(allowed)})"
        )

    # 7B：任意进入 LIVE_READONLY 均需 PRODUCTION_READY（含 SHADOW→LIVE_READONLY）
    if dst == "LIVE_READONLY" and not production_ready:
        raise EnvironmentTransitionError(
            "→LIVE_READONLY requires PRODUCTION_READY=true"
        )

    return dst


def current_allowed_targets(from_env: str) -> tuple[str, ...]:
    """返回当前环境下 7A 可转换目标（调试/文档用）。"""
    src = str(from_env or "PAPER").strip().upper()
    return tuple(sorted(_TRANSITIONS.get(src, frozenset()) & _ALLOWED_7A))
