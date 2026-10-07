"""算子注册：P0 仅 factor_lab DSL 模板。"""

from __future__ import annotations

from typing import Callable

from .ast import ExpressionNode

LOWERERS: dict[str, Callable[[ExpressionNode], str]] = {}


def register_lowerer(kind: str, fn: Callable[[ExpressionNode], str]) -> None:
    LOWERERS[kind] = fn


def supported_kinds() -> frozenset[str]:
    return frozenset(LOWERERS.keys())


__all__ = ["LOWERERS", "register_lowerer", "supported_kinds"]
