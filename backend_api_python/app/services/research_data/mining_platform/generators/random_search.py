"""random_search：seed 可复现采样。"""

from __future__ import annotations

import random

from ..expression.ast import (
    ColumnNode,
    ExpressionNode,
    MomentumNode,
    RatioNode,
    RefNode,
    RollingMeanNode,
    RollingStdNode,
    VolatilityNode,
    node_depth,
)
from ..expression.canonicalize import expression_hash_from_node
from ..generators.exhaustive import assert_node_within_policy, ComplexityLimitError
from ..policy import MiningPolicy


def _pool(policy: MiningPolicy, columns: tuple[str, ...]) -> list[ExpressionNode]:
    from .exhaustive import generate_exhaustive

    # 用 exhaustive 全集作采样池（再 shuffle）
    return generate_exhaustive(
        policy.model_copy(update={"max_candidates": policy.max_candidates * 4}),
        columns=columns,
    )


def generate_random(
    policy: MiningPolicy,
    *,
    columns: tuple[str, ...],
    random_seed: int,
) -> list[ExpressionNode]:
    rng = random.Random(int(random_seed))
    pool = _pool(policy, columns)
    if not pool:
        # fallback 单模板
        pool = [MomentumNode(window=policy.momentum_windows[0])]
    rng.shuffle(pool)
    out: list[ExpressionNode] = []
    seen: set[str] = set()
    for n in pool:
        try:
            assert_node_within_policy(n, policy)
        except ComplexityLimitError:
            continue
        _, eh = expression_hash_from_node(n)
        if eh in seen:
            continue
        seen.add(eh)
        out.append(n)
        if len(out) >= policy.max_candidates:
            break
    return out


__all__ = ["generate_random"]
