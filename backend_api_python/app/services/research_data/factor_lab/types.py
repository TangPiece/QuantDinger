"""Factor Lab 枚举与布局选择规则（无 qlib 类型）。"""

from __future__ import annotations

from typing import Literal

FactorType = Literal[
    "TECHNICAL",
    "FUNDAMENTAL",
    "MICROSTRUCTURE",
    "LEVEL2",
    "ALTERNATIVE",
    "ML_DERIVED",
    "COMPOSITE",
    "CUSTOM",
]

InformationPolicy = Literal["PIT_SAFE", "NON_PIT", "UNKNOWN"]

ComputationEngine = Literal["qlib", "quantdinger", "duckdb", "polars", "level2"]

StorageLayout = Literal["long", "wide"]

DEPENDENCY_TYPES: frozenset[str] = frozenset(
    {
        "market",
        "fundamental",
        "corporate_action",
        "trading_status",
        "universe",
        "level2",
        "factor",
        "other",
    }
)

SCHEMA_LONG = "factor_daily_long@1"
SCHEMA_WIDE = "factor_daily_wide@1"


def recommend_layout(
    *,
    factor_type: str,
    n_columns: int = 1,
    information_policy: str = "UNKNOWN",
) -> StorageLayout:
    """Wide/Long 选择规则（4A 文档化；4B 执行）。

    - 单因子 / 稀疏 / PIT 财务 → long
    - 大规模标准集（多列）→ wide
    """
    if information_policy == "PIT_SAFE" or factor_type == "FUNDAMENTAL":
        return "long"
    if n_columns > 8:
        return "wide"
    return "long"
