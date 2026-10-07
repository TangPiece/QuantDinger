"""AST → factor_lab DSL 字符串。"""

from __future__ import annotations

from .ast import (
    ColumnNode,
    ExpressionNode,
    MomentumNode,
    RatioNode,
    RefNode,
    RollingMeanNode,
    RollingStdNode,
    VolatilityNode,
)
from .operators import register_lowerer


class LowerDSLError(ValueError):
    pass


def lower_to_dsl(node: ExpressionNode) -> str:
    kind = getattr(node, "kind", "")
    if kind == "column":
        n = node  # type: ignore[assignment]
        assert isinstance(n, ColumnNode)
        return n.name.lower()
    if kind == "momentum":
        n = node  # type: ignore[assignment]
        assert isinstance(n, MomentumNode)
        return f"momentum_{int(n.window)}"
    if kind == "volatility":
        n = node  # type: ignore[assignment]
        assert isinstance(n, VolatilityNode)
        return f"volatility_{int(n.window)}"
    if kind == "rolling_mean":
        n = node  # type: ignore[assignment]
        assert isinstance(n, RollingMeanNode)
        return f"rolling_mean_{int(n.window)}({n.field.lower()})"
    if kind == "rolling_std":
        n = node  # type: ignore[assignment]
        assert isinstance(n, RollingStdNode)
        return f"rolling_std_{int(n.window)}({n.field.lower()})"
    if kind == "ref":
        n = node  # type: ignore[assignment]
        assert isinstance(n, RefNode)
        return f"Ref({n.field.lower()}, {int(n.lag)})"
    if kind == "ratio":
        n = node  # type: ignore[assignment]
        assert isinstance(n, RatioNode)
        return f"{n.numerator.lower()}/{n.denominator.lower()}"
    raise LowerDSLError(f"unsupported node kind: {kind!r}")


def _register() -> None:
    for k in (
        "column",
        "momentum",
        "volatility",
        "rolling_mean",
        "rolling_std",
        "ref",
        "ratio",
    ):
        register_lowerer(k, lower_to_dsl)


_register()

__all__ = ["LowerDSLError", "lower_to_dsl"]
