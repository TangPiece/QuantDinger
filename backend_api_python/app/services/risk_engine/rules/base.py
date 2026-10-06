"""RiskRule Protocol。"""

from __future__ import annotations

from typing import Protocol

from ..protocol import RiskContext, RiskResult


class RiskRule(Protocol):
    """可组合风控规则。"""

    code: str

    def evaluate(self, context: RiskContext) -> list[RiskResult]: ...
