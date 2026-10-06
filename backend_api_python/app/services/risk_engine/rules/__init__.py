"""P0 规则导出。"""

from .account_state import AccountStateRule
from .data_freshness import DataFreshnessRule
from .delta_limit import DeltaLimitRule
from .exposure_limit import ExposureLimitRule
from .position_limit import PositionLimitRule
from .signal_freshness import SignalFreshnessRule
from .trading_status import TradingStatusRule
from .turnover_limit import TurnoverLimitRule
from .universe import UniverseRule


def default_rules():
    """P0 规则集（顺序：账户 → 状态 → 限额 → 敞口）。"""
    return [
        AccountStateRule(),
        UniverseRule(),
        TradingStatusRule(),
        DataFreshnessRule(),
        SignalFreshnessRule(),
        PositionLimitRule(),
        DeltaLimitRule(),
        TurnoverLimitRule(),
        ExposureLimitRule(),
    ]


__all__ = [
    "AccountStateRule",
    "DataFreshnessRule",
    "DeltaLimitRule",
    "ExposureLimitRule",
    "PositionLimitRule",
    "SignalFreshnessRule",
    "TradingStatusRule",
    "TurnoverLimitRule",
    "UniverseRule",
    "default_rules",
]
