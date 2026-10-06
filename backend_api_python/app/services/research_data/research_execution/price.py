"""ExecutionPricePolicy 校验：禁止复权价当真成交。"""

from __future__ import annotations

from .protocol import ExecutionPricePolicy


def assert_execution_price_raw(policy: ExecutionPricePolicy | None = None) -> ExecutionPricePolicy:
    """v1 仅允许 adjustment=none。"""
    p = policy or ExecutionPricePolicy()
    if p.adjustment != "none":
        raise ValueError(
            "execution_price_adjustment must be 'none' in 5C v1 "
            "(do not use adjusted prices as fill prices)"
        )
    return p
