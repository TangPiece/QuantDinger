"""L2 百因子日频并行链路：Parquet 宽表 + D1 元数据。

与旧 ``calc_daily_factors`` → D1 ``l2_factors`` 热表链路并存，不改图表读侧。
"""
from .catalog import ALL_GROUPS, FACTOR_DEFINITIONS, FACTOR_VERSION, factor_ids, wide_columns
from .orchestrator import process_day_group, run

__all__ = [
    "ALL_GROUPS",
    "FACTOR_DEFINITIONS",
    "FACTOR_VERSION",
    "factor_ids",
    "wide_columns",
    "process_day_group",
    "run",
]
