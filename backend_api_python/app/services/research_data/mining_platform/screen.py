"""Fast Screen：轻量 IC / 合法性。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .expression.ast import ExpressionNode
from .expression.canonicalize import expression_hash_from_node
from .expression.lower_dsl import lower_to_dsl
from .policy import MiningPolicy
from .protocol import MiningPlatformInject


@dataclass
class ScreenResult:
    passed: bool
    reason: str = ""
    proxy_ic: float = 0.0


def fast_screen_node(
    node: ExpressionNode,
    policy: MiningPolicy,
    *,
    inject: MiningPlatformInject | None = None,
    proxy_ic_by_hash: Mapping[str, float] | None = None,
) -> ScreenResult:
    if inject and inject.fast_screen_pass_all:
        return ScreenResult(passed=True, proxy_ic=0.05)

    try:
        dsl = lower_to_dsl(node)
    except Exception as exc:
        return ScreenResult(passed=False, reason=f"dsl_lower_failed:{exc}")

    canon, eh = expression_hash_from_node(node)
    _ = canon

    threshold = policy.fast_screen_min_ic
    if inject and inject.screen_ic_threshold is not None:
        threshold = float(inject.screen_ic_threshold)

    ic = 0.0
    if proxy_ic_by_hash and eh in proxy_ic_by_hash:
        ic = float(proxy_ic_by_hash[eh])
    elif inject and inject.synthetic_evaluation_scores and eh in inject.synthetic_evaluation_scores:
        ic = float(inject.synthetic_evaluation_scores[eh])
    else:
        # 确定性伪 IC：hash 前 8 位 → [0,1)
        ic = (int(eh[:8], 16) % 1000) / 1000.0

    if ic < threshold:
        return ScreenResult(passed=False, reason="ic_below_threshold", proxy_ic=ic)
    return ScreenResult(passed=True, proxy_ic=ic)


__all__ = ["ScreenResult", "fast_screen_node"]
