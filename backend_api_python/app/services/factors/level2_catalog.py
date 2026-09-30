"""Level2 日频因子目录。列名必须与 level2 仓库 ``strategy/factors/names.py`` 一致。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Level2FactorSpec:
    """一个可在因子库里展示的 Level2 因子。"""

    factor_id: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    direction_hint: str


# (factor_id, 中文名, 英文名, 中文说明, 英文说明, 方向)
_BASE_SPECS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "l2_spread",
        "买卖价差",
        "Quoted spread",
        "连续竞价买一卖一相对中间价的平均价差，数值越低通常表示报价更紧。",
        "Average continuous-trading spread of the best bid and ask relative to the mid price.",
        "lower_is_bullish",
    ),
    (
        "l2_depth_bid",
        "十档买量",
        "Ten-level bid depth",
        "连续竞价十档申买量合计的时间均值。",
        "Time average of the summed ten-level bid size during continuous trading.",
        "higher_is_bullish",
    ),
    (
        "l2_depth_ask",
        "十档卖量",
        "Ten-level ask depth",
        "连续竞价十档申卖量合计的时间均值。",
        "Time average of the summed ten-level ask size during continuous trading.",
        "lower_is_bullish",
    ),
    (
        "l2_obi",
        "订单簿不平衡",
        "Order book imbalance",
        "十档买量减十档卖量，再除以两边之和。正值表示买盘更厚。",
        "Ten-level bid size minus ask size, divided by their sum. Positive means thicker bids.",
        "higher_is_bullish",
    ),
    (
        "l2_order_ratio",
        "委比",
        "Order-book ratio",
        "叫买总量减叫卖总量，再除以两边之和。",
        "Total bid orders minus total ask orders, divided by their sum.",
        "higher_is_bullish",
    ),
    (
        "l2_active_net_buy",
        "主动净买入率",
        "Active net buy ratio",
        "主动买成交额减主动卖成交额，再除以总成交额。方向来自逐笔 BS 标志。",
        "Active buy amount minus active sell amount, divided by total trade amount.",
        "higher_is_bullish",
    ),
    (
        "l2_big_net_inflow_rate",
        "大单净流入率",
        "Large-order net inflow",
        "同一委托聚合成交额达到 100 万元视为大单，大单净买入额除以总成交额。",
        "Net buy amount of orders that fill at least 1 million yuan, divided by total amount.",
        "higher_is_bullish",
    ),
    (
        "l2_cancel_ratio",
        "撤单率",
        "Cancel ratio",
        "09:25 之后的撤单量除以撤单量与成交量之和。深市看成交撤单代码，沪市看委托撤单。",
        "Cancel size after 09:25 divided by cancel size plus trade size.",
        "lower_is_bullish",
    ),
    (
        "l2_auction_amount",
        "集合竞价成交额",
        "Opening auction amount",
        "09:30 前价格大于 0 的成交额，含 09:25 撮合，单位元。",
        "Trade amount before 09:30 with a positive price, including the 09:25 print. Yuan.",
        "neutral",
    ),
    (
        "l2_auction_imbalance",
        "竞价委比",
        "Auction order imbalance",
        "09:15 至 09:25 未撤有效委托的买量减卖量，再除以两边之和。",
        "Uncancelled bid size minus ask size during the 09:15-09:25 auction, divided by their sum.",
        "higher_is_bullish",
    ),
    (
        "l2_ret_overnight",
        "隔夜收益",
        "Overnight return",
        "开盘价除以前收盘再减 1，也就是开盘高开幅度。",
        "Open divided by the previous close, minus 1.",
        "neutral",
    ),
    (
        "l2_ret_open_30",
        "开盘三十分钟收益",
        "First 30-minute return",
        "10:00 附近价格相对开盘价的收益。",
        "Return from the official open to the price around 10:00.",
        "neutral",
    ),
    (
        "l2_ret_tail_30",
        "尾盘三十分钟收益",
        "Last 30-minute return",
        "收盘附近价格相对 14:30 附近价格的收益。",
        "Return from the price around 14:30 to the close.",
        "neutral",
    ),
    (
        "l2_ret_intraday",
        "日内收益",
        "Intraday return",
        "收盘价除以开盘价再减 1。",
        "Close divided by the open, minus 1.",
        "neutral",
    ),
    (
        "l2_rv",
        "已实现波动",
        "Realized volatility",
        "连续竞价相邻 1 分钟对数收益的平方和再开方。午休缺口不计入。",
        "Square root of summed squared one-minute log returns. The lunch gap is skipped.",
        "lower_is_bullish",
    ),
    (
        "l2_rskew",
        "已实现偏度",
        "Realized skewness",
        "连续竞价相邻 1 分钟对数收益的三阶矩，除以平方和的 1.5 次方。",
        "Third moment of one-minute log returns divided by the 1.5 power of the second moment.",
        "neutral",
    ),
)

_WINDOWS = (5, 10, 20)
_STATS = {
    "mean": ("均值", "mean"),
    "std": ("标准差", "standard deviation"),
    "skew": ("偏度", "skewness"),
}


def level2_factor_specs() -> tuple[Level2FactorSpec, ...]:
    """基础因子以及 5/10/20 日均值、标准差、偏度。"""
    specs = [
        Level2FactorSpec(*item)
        for item in _BASE_SPECS
    ]
    for base in specs.copy():
        for window in _WINDOWS:
            for stat, (zh_stat, en_stat) in _STATS.items():
                specs.append(Level2FactorSpec(
                    factor_id=f"{base.factor_id}_{stat}_{window}",
                    name_zh=f"{base.name_zh}{window}日{zh_stat}",
                    name_en=f"{base.name_en} {window}-day {en_stat}",
                    description_zh=f"{base.description_zh}过去 {window} 个交易日（含当日）的{zh_stat}。",
                    description_en=f"{base.description_en} {window}-day {en_stat} including the current session.",
                    direction_hint=base.direction_hint,
                ))
    return tuple(specs)


def base_factor_ids() -> tuple[str, ...]:
    """不含滚动列的基础因子 id，和离线计算结果列名相同。"""
    return tuple(item[0] for item in _BASE_SPECS)
