"""薄 AST：仅 DSL 模板组合（非 GP 树）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

NodeKind = Literal[
    "column",
    "momentum",
    "volatility",
    "rolling_mean",
    "rolling_std",
    "ref",
    "ratio",
]


@dataclass(frozen=True)
class ColumnNode:
    kind: Literal["column"] = "column"
    name: str = "close"


@dataclass(frozen=True)
class MomentumNode:
    kind: Literal["momentum"] = "momentum"
    window: int = 5


@dataclass(frozen=True)
class VolatilityNode:
    kind: Literal["volatility"] = "volatility"
    window: int = 10


@dataclass(frozen=True)
class RollingMeanNode:
    kind: Literal["rolling_mean"] = "rolling_mean"
    window: int = 5
    field: str = "close"


@dataclass(frozen=True)
class RollingStdNode:
    kind: Literal["rolling_std"] = "rolling_std"
    window: int = 5
    field: str = "close"


@dataclass(frozen=True)
class RefNode:
    kind: Literal["ref"] = "ref"
    field: str = "close"
    lag: int = 1


@dataclass(frozen=True)
class RatioNode:
    kind: Literal["ratio"] = "ratio"
    numerator: str = "close"
    denominator: str = "open"


ExpressionNode = Union[
    ColumnNode,
    MomentumNode,
    VolatilityNode,
    RollingMeanNode,
    RollingStdNode,
    RefNode,
    RatioNode,
]


def node_depth(node: ExpressionNode) -> int:
    return 1


__all__ = [
    "ColumnNode",
    "ExpressionNode",
    "MomentumNode",
    "RatioNode",
    "RefNode",
    "RollingMeanNode",
    "RollingStdNode",
    "VolatilityNode",
    "node_depth",
]
