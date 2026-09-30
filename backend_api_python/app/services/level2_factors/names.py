"""日频因子列名。QuantDinger 侧注册表必须与 ``BASE_FACTORS`` 保持同名。"""
from __future__ import annotations

# 单日基础列。滚动列由 ``rollup_name`` 派生，不在此重复列出。
BASE_FACTORS: tuple[str, ...] = (
    "l2_spread",
    "l2_depth_bid",
    "l2_depth_ask",
    "l2_obi",
    "l2_order_ratio",
    "l2_active_net_buy",
    "l2_big_net_inflow_rate",
    "l2_cancel_ratio",
    "l2_auction_amount",
    "l2_auction_imbalance",
    "l2_ret_overnight",
    "l2_ret_open_30",
    "l2_ret_tail_30",
    "l2_ret_intraday",
    "l2_rv",
    "l2_rskew",
)

# 大单：按委托号聚合成交额，达到该金额（元）才计入大单。
BIG_ORDER_AMOUNT = 1_000_000.0

# 原始价格是「元 × 10000」的整数。比率类因子除不除这个常数结果一样。
PRICE_SCALE = 10_000.0

ROLL_WINDOWS: tuple[int, ...] = (5, 10, 20)
ROLL_STATS: tuple[str, ...] = ("mean", "std", "skew")


def rollup_name(base: str, stat: str, window: int) -> str:
    """滚动列名，例如 ``l2_obi_mean_20``。窗口含当日，且只使用当日及更早的交易日。"""
    return f"{base}_{stat}_{window}"


def stored_columns() -> list[str]:
    """按日宽表落盘列。5/10/20 日均值、标准差和偏度不写入，读取时再算。"""
    return ["trade_date", "symbol", *BASE_FACTORS]


def all_factor_columns() -> list[str]:
    """基础列加全部 5/10/20 日均值、标准差、偏度。供读取后现算，不是落盘列。"""
    columns = list(BASE_FACTORS)
    for base in BASE_FACTORS:
        for window in ROLL_WINDOWS:
            for stat in ROLL_STATS:
                columns.append(rollup_name(base, stat, window))
    return columns
