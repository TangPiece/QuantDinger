"""exhaustive_small：模板参数网格。"""

from __future__ import annotations

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
from ..policy import MiningPolicy


class ComplexityLimitError(ValueError):
    pass


def generate_exhaustive(policy: MiningPolicy, *, columns: tuple[str, ...]) -> list[ExpressionNode]:
    nodes: list[ExpressionNode] = []
    allowed = {c.lower() for c in columns} | {c.lower() for c in policy.base_columns}

    for col in sorted(allowed):
        if policy.max_depth >= 1:
            nodes.append(ColumnNode(name=col))

    for w in policy.momentum_windows:
        if w > policy.max_window:
            continue
        nodes.append(MomentumNode(window=w))

    for w in policy.volatility_windows:
        if w > policy.max_window:
            continue
        nodes.append(VolatilityNode(window=w))

    for w in policy.rolling_windows:
        if w > policy.max_window:
            continue
        for field in policy.rolling_fields:
            if field.lower() not in allowed and field.lower() not in {
                "close",
                "open",
                "high",
                "low",
                "volume",
            }:
                continue
            nodes.append(RollingMeanNode(window=w, field=field))
            if policy.max_depth >= 2:
                nodes.append(RollingStdNode(window=w, field=field))

    for lag in policy.ref_windows:
        if lag > policy.max_window:
            continue
        for field in ("close", "open"):
            nodes.append(RefNode(field=field, lag=lag))

    for num, den in policy.ratio_pairs:
        nodes.append(RatioNode(numerator=num, denominator=den))

    out: list[ExpressionNode] = []
    seen: set[str] = set()
    from ..expression.canonicalize import expression_hash_from_node

    for n in nodes:
        if node_depth(n) > policy.max_depth:
            continue
        canon, eh = expression_hash_from_node(n)
        if eh in seen:
            continue
        seen.add(eh)
        out.append(n)
        if len(out) >= policy.max_candidates:
            break

    if len(nodes) > policy.max_candidates and len(out) >= policy.max_candidates:
        pass  # 截断符合 max_candidates
    return out


def assert_node_within_policy(node: ExpressionNode, policy: MiningPolicy) -> None:
    if node_depth(node) > policy.max_depth:
        raise ComplexityLimitError(f"depth exceeds max_depth={policy.max_depth}")
    kind = getattr(node, "kind", "")
    w = getattr(node, "window", None) or getattr(node, "lag", None)
    if w is not None and int(w) > policy.max_window:
        raise ComplexityLimitError(f"window {w} exceeds max_window={policy.max_window}")


__all__ = ["ComplexityLimitError", "assert_node_within_policy", "generate_exhaustive"]
