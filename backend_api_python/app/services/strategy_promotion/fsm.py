"""Phase 8D：环境晋升边校验（禁跨级 / SHADOW→LIVE）。"""

from __future__ import annotations

from .protocol import PromotionEnvironment, PromotionStageName

# 合法单步环境边
_ENV_EDGES: dict[str, str] = {
    "REGISTERED": "SHADOW",
    "SHADOW": "CONTROLLED_LIVE",
    "CONTROLLED_LIVE": "LIVE",
}

_FORBIDDEN_SKIP = frozenset(
    {
        ("REGISTERED", "CONTROLLED_LIVE"),
        ("REGISTERED", "LIVE"),
        ("SHADOW", "LIVE"),
        ("SHADOW", "REGISTERED"),
        ("CONTROLLED_LIVE", "SHADOW"),
        ("LIVE", "SHADOW"),
        ("LIVE", "CONTROLLED_LIVE"),
        ("LIVE", "REGISTERED"),
    }
)


class InvalidPromotionTransitionError(RuntimeError):
    """非法环境晋升。"""


def assert_environment_transition(
    from_env: PromotionEnvironment,
    to_env: PromotionEnvironment,
) -> None:
    """校验 REGISTERED→SHADOW→CONTROLLED_LIVE→LIVE 单步前进。"""
    src = str(from_env).upper()
    dst = str(to_env).upper()
    if src == dst:
        raise InvalidPromotionTransitionError(f"no-op transition {src}→{dst}")
    if (src, dst) in _FORBIDDEN_SKIP:
        raise InvalidPromotionTransitionError(f"skip-level or forbidden: {src}→{dst}")
    expected = _ENV_EDGES.get(src)
    if expected != dst:
        raise InvalidPromotionTransitionError(
            f"transition {src}→{dst} not allowed (expected next: {expected})"
        )


def stages_for_transition(
    from_env: PromotionEnvironment,
    to_env: PromotionEnvironment,
) -> list[PromotionStageName]:
    """按目标环境返回编排阶段（LIVE 永不自动，仅 GOV_LIVE / ELIGIBLE）。"""
    dst = str(to_env).upper()
    base: list[PromotionStageName] = ["ELIGIBLE_CHECK", "REGISTRY_BIND"]
    if dst == "SHADOW":
        return base + ["GOV_SHADOW", "SHADOW_SESSION"]
    if dst == "CONTROLLED_LIVE":
        return base + ["GOV_CONTROLLED_LIVE", "CL_SESSION"]
    if dst == "LIVE":
        return base + ["GOV_LIVE", "LIVE_ELIGIBLE"]
    raise InvalidPromotionTransitionError(f"unknown target environment: {dst}")


__all__ = [
    "InvalidPromotionTransitionError",
    "assert_environment_transition",
    "stages_for_transition",
]
